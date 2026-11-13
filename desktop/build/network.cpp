// license:BSD-3-Clause
// copyright-holders:Luke McMillan
// Open Motion output transport for MAME 0.276. One ordered, owning write queue
// per client; all socket and client-set work stays on the ASIO thread.
#include "output_module.h"
#include "modules/lib/osdobj_common.h"
#include "modules/osdmodule.h"
#include "emu.h"
#include "asio.h"
#include <deque>
#include <memory>
#include <set>
#include <string>
#include <thread>

namespace osd { namespace {
class session : public std::enable_shared_from_this<session>
{
public:
    session(asio::ip::tcp::socket socket) : m_socket(std::move(socket)) { }
    void send(std::string message)
    {
        if (!m_socket.is_open()) return;
        // Disconnect a stalled consumer instead of replaying a long motion backlog.
        if (m_messages.size() >= 512) { close(); return; }
        bool const idle = m_messages.empty();
        m_messages.push_back(std::move(message));
        if (idle) write();
    }
    bool open() const { return m_socket.is_open(); }
    void close()
    {
        std::error_code ec;
        m_socket.close(ec);
    }
private:
    void write()
    {
        auto self = shared_from_this();
        asio::async_write(m_socket, asio::buffer(m_messages.front()),
            [this,self](std::error_code ec, std::size_t) {
                if (ec) { close(); return; }
                m_messages.pop_front();
                if (!m_messages.empty() && open()) write();
            });
    }
    asio::ip::tcp::socket m_socket;
    std::deque<std::string> m_messages;
};
class output_network : public osd_module, public output_module
{
public:
    output_network() : osd_module(OSD_OUTPUT_PROVIDER,"network"), output_module() { }
    virtual ~output_network() { shutdown(); }
    virtual int init(osd_interface &osd, const osd_options &) override
    {
        auto &machine = downcast<osd_common_t &>(osd).machine();
        m_start = util::string_format("mame_start = %s\r",machine.system().name);
        m_context = std::make_unique<asio::io_context>();
        m_acceptor = std::make_unique<asio::ip::tcp::acceptor>(*m_context);
        std::error_code ec;
        asio::ip::tcp::endpoint endpoint(asio::ip::address_v4::loopback(),8000);
        m_acceptor->open(endpoint.protocol(),ec);
        if (!ec) m_acceptor->bind(endpoint,ec);
        if (!ec) m_acceptor->listen(asio::ip::tcp::socket::max_listen_connections,ec);
        if (ec) { osd_printf_error("Open Motion output bind: %s\n",ec.message()); return -1; }
        accept();
        m_thread = std::thread([this](){m_context->run();});
        return 0;
    }
    virtual void notify(const char *name, int32_t value) override
    {
        if (!m_context || !m_thread.joinable()) return;
        auto message = util::string_format("%s = %d\r",name ? name : "none",value);
        asio::post(*m_context,[this,message=std::move(message)]() {
            for (auto it=m_clients.begin();it!=m_clients.end();) {
                if (!(*it)->open()) it=m_clients.erase(it);
                else {(*it)->send(message);++it;}
            }
        });
    }
    virtual void exit() override { shutdown(); }
private:
    void accept()
    {
        m_acceptor->async_accept([this](std::error_code ec,asio::ip::tcp::socket socket) {
            if (!ec) {
                std::error_code option_error;
                socket.set_option(asio::ip::tcp::no_delay(true),option_error);
                auto client=std::make_shared<session>(std::move(socket));
                m_clients.insert(client);
                client->send(m_start);
            }
            if (m_acceptor->is_open()) accept();
        });
    }
    void shutdown()
    {
        if (m_context) m_context->stop();
        if (m_thread.joinable()) m_thread.join();
        m_clients.clear();
        m_acceptor.reset();
        m_context.reset();
    }
    std::unique_ptr<asio::io_context> m_context;
    std::unique_ptr<asio::ip::tcp::acceptor> m_acceptor;
    std::thread m_thread;
    std::set<std::shared_ptr<session>> m_clients;
    std::string m_start;
};
} }
MODULE_DEFINITION(OUTPUT_NETWORK,osd::output_network)
