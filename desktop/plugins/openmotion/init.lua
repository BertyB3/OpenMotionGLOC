-- Open Motion: G-LOC. Copyright Luke McMillan. See repository LICENSE.TXT.
-- No serial access here. The host bridge reports what was actually written.
local exports = { name='openmotion', version='0.1.0', description='Open Motion monitor',
                  license='See LICENSE.TXT', author={ name='Luke McMillan' } }
function exports.startplugin()
    local frame, view, pressed = 0, 1, false
    local token = tonumber(os.getenv('OPEN_MOTION_SESSION') or '0')
    local status_path = os.getenv('OPEN_MOTION_STATUS')
    local profile = os.getenv('OPEN_MOTION_PROFILE') or 'gloc'
    local key_token = os.getenv('OPEN_MOTION_OVERLAY_KEY') or 'KEYCODE_F6'
    if os.getenv('OPEN_MOTION_OVERLAY') == '0' then view = 0 end
    local maps = {
        gforce2gloc = {'left_motor_position_nor','right_motor_position_nor','left_motor_speed','right_motor_speed'},
        gloc = {'left_motor_position_nor','right_motor_position_nor','left_motor_speed','right_motor_speed'},
        strkfgtr = {'left_motor_position_nor','right_motor_position_nor','left_motor_speed','right_motor_speed'},
        aburner2 = {'gloc_q','gloc_r','left_motor_speed','right_motor_speed'},
        wingwar360 = {'gloc_q','gloc_r','left_motor_speed','right_motor_speed'},
        sharrierglc = {'gloc_q_target','gloc_r_target','left_motor_speed','right_motor_speed'},
        sharrier1glc = {'gloc_q_target','gloc_r_target','left_motor_speed','right_motor_speed'}
    }
    local map = maps[profile]
    local pose, report, age = nil, nil, 999
    local function clamp(v,lo,hi) return math.max(lo,math.min(hi,v)) end
    local function sample()
        local m = manager.machine
        local out = m.output
        if profile == 'gforce2gloc' then
            local port=m.ioport.ports[':GLOCMOTION']
            if port then port:field(1).user_value=1 end
        end
        frame = frame + 1
        local valid = map ~= nil and token > 0
        local values = {}
        if valid then
            for i,name in ipairs(map) do
                if out:name_to_id(name) == 0 then valid = false end
                values[i] = out:get_value(name)
            end
        end
        if valid then
            -- Original MAMEHooker mapping is identity. Conversion drivers expose
            -- their already-inverted, cabinet-space targets under explicit names.
            local q,r = values[1], values[2]
            if profile == 'gforce2gloc' then q,r=32-q,32-r end
            local s,t = values[3], values[4]
            valid = q >= 0 and q <= 32 and r >= 0 and r <= 32 and s >= 0 and s <= 7 and t >= 0 and t <= 7
            if valid then
                q,r,s,t = clamp(q,1,32),clamp(r,1,32),clamp(s,1,7),clamp(t,1,7)
                local a = out:get_value('start_lamp') > 0 and 1 or 0
                local b = out:get_value('danger_lamp') > 0 and 1 or 0
                pose = {q,r,s,t,a,b}
                local packet = q+r*64+s*4096+t*32768+a*262144+b*524288+1048576
                -- Toggle bit 21 so a new client receives an unchanged held pose.
                out:set_value('om_packet',packet+(frame%2)*2097152)
            end
        end
        if not valid then pose=nil; out:set_value('om_packet',0) end
        -- Alternate sign to resend the session token after a delayed connection.
        out:set_value('om_session',frame%2 == 0 and token or -token)
        out:set_value('om_frame',frame)
        out:set_value('om_paused',m.paused and 1 or 0)
    end
    local function read_report()
        age = age + 1
        if not status_path then return end
        local f = io.open(status_path,'r')
        if not f then return end
        local lines = {}
        for line in f:lines() do lines[#lines+1]=line end
        f:close()
        if tonumber(lines[1]) ~= token then return end
        if report == nil or lines[3] ~= report[3] then age = 0 end
        report = lines
    end
    local function draw()
        local m = manager.machine
        local code = m.input:code_from_token(key_token)
        local down = m.input:code_pressed(code)
        if down and not pressed then view=(view+1)%3 end
        pressed=down
        read_report()
        if view == 0 then return end
        local c = m.render.ui_container
        local live = report and age < 120 and os.time()-tonumber(report[3]) < 2
        local mode = live and (report[2]=='1' and 'MOTION ON' or 'MONITOR ONLY') or 'BRIDGE OFFLINE'
        c:draw_box(0,0,1,view==1 and 0.20 or 0.43,0xe0101010,0xe0101010)
        local line = 'Q-- R-- S- T-'
        if pose then line=string.format('Q%02d R%02d S%d T%d',pose[1],pose[2],pose[3],pose[4]) end
        c:draw_text(0.02,0.01,'OPEN MOTION  '..line,0xffff7900)
        c:draw_text(0.02,0.08,mode..' | F6 VIEW',0xffffffff)
        if view==2 then
            c:draw_text(0.02,0.15,'TX '..(live and report[4] or 'None'),0xffffffff)
            c:draw_text(0.02,0.22,'RX '..(live and report[5]:sub(1,45) or 'None'),0xffbbbbbb)
            c:draw_text(0.02,0.29,'Targets sent; position unverified',0xffbbbbbb)
            c:draw_text(0.02,0.36,'Frame '..frame..' | '..profile,0xffbbbbbb)
        end
    end
    emu.register_frame(sample)
    emu.register_frame_done(draw,'frame')
    emu.register_pause(function() manager.machine.output:set_value('om_paused',1) end)
    emu.register_resume(function() manager.machine.output:set_value('om_paused',0) end)
end
return exports
