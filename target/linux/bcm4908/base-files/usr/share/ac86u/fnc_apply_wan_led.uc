// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_apply_wan_led.uc</FILE> - <DESC>Apply an already-authorized WAN indicator state without disturbing a correct activity trigger.</DESC>
// <VERS>VERSION: 0.1.2</VERS>
// <WCTX>Keep WAN colours exclusive and preserve normal white link/activity behavior.</WCTX>
// <CLOG>Restore intended brightness after replacing a trigger, which clears the old LED level.</CLOG>

export function apply_wan_led(ctx, state) {
    if (state != "off" && state != "white" && state != "red")
        die("Unknown WAN indicator state");
    let order = state == "red" ? ["wan", "wan-error"] : ["wan-error", "wan"];
    let changed = 0;
    for (let i = 0; i < length(order); i++) {
        let name = order[i], base = ctx.paths.sysfs + "/" + name;
        let trigger = ctx.fs.readfile(base + "/trigger");
        let brightness = ctx.fs.readfile(base + "/brightness");
        let maximum = ctx.fs.readfile(base + "/max_brightness");
        if (type(trigger) != "string" || type(brightness) != "string" ||
            type(maximum) != "string" || !match(trim(maximum), /^[1-9][0-9]*$/))
            die("Cannot read valid WAN LED controls: " + base);
        let netdev = name == "wan" && state == "white";
        let level = name == "wan-error" && state == "red" ? trim(maximum) : "0";
        let writes = [];
        if (!netdev) {
            let trigger_changed = index(trigger, "[none]") < 0;
            if (trigger_changed) push(writes, [base + "/trigger", "none\n"]);
            if (trigger_changed || trim(brightness) != level)
                push(writes, [base + "/brightness", level + "\n"]);
        }
        else if (index(trigger, "[netdev]") < 0) {
            push(writes, [base + "/trigger", "netdev\n"]);
            push(writes, [base + "/brightness", trim(maximum) + "\n"]);
        }
        for (let n = 0; n < length(writes); n++) {
            if (ctx.fs.writefile(writes[n][0], writes[n][1]) != length(writes[n][1]))
                die("WAN LED write failed: " + writes[n][0]);
            changed++;
        }
        if (netdev) {
            let options = [["device_name", "wan"], ["link", "1"], ["rx", "1"], ["tx", "1"]];
            for (let n = 0; n < length(options); n++) {
                let path = base + "/" + options[n][0], value = ctx.fs.readfile(path);
                if (type(value) != "string") die("Cannot read netdev LED control: " + path);
                if (trim(value) == options[n][1]) continue;
                let data = options[n][1] + "\n";
                if (ctx.fs.writefile(path, data) != length(data))
                    die("WAN netdev LED write failed: " + path);
                changed++;
            }
        }
    }
    return changed;
};

// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_apply_wan_led.uc</FILE> - <DESC>Apply an already-authorized WAN indicator state without disturbing a correct activity trigger.</DESC>
// <VERS>END OF VERSION: 0.1.2</VERS>
