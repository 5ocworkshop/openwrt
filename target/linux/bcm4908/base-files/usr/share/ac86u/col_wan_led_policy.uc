// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/col_wan_led_policy.uc</FILE> - <DESC>Normalize kernel link/default-route snapshots into the approved WAN indicator state.</DESC>
// <VERS>VERSION: 0.1.2</VERS>
// <WCTX>Use physical carrier and installed routes rather than logical WAN interface status.</WCTX>
// <CLOG>Use the native separator-first join API when recognizing the stock WAN activity mapping.</CLOG>

export function wan_led_snapshot(links, routes) {
    if (type(links) != "array" || type(routes) != "array")
        die("Link and route snapshots must be arrays");
    let carrier = false, has_default = false;
    for (let i = 0; i < length(links); i++) {
        let link = links[i];
        if (type(link) != "object") die("Malformed link record");
        if (link.ifname != "wan") continue;
        let flags = type(link.flags) == "array" ? link.flags[0] : link.flags;
        if (type(flags) != "int" || type(link.carrier) != type(true))
            die("Malformed WAN carrier or interface flags");
        carrier = !!(flags & 1) && link.carrier;
    }
    for (let i = 0; i < length(routes); i++) {
        let route = routes[i];
        if (type(route) != "object" || type(route.family) != "int" ||
            type(route.table) != "int" || type(route.type) != "int")
            die("Malformed route record");
        if (route.table != 254 || route.type != 1) continue;
        if (route.family == 2 && (route.dst == null || route.dst == "0.0.0.0/0"))
            has_default = true;
        if (route.family == 10 && (route.dst == null || route.dst == "::/0"))
            has_default = true;
    }
    return { carrier, has_default, state: !carrier ? "off" : has_default ? "white" : "red" };
};

export function wan_led_overrides(system) {
    if (type(system) != "object") die("Invalid system LED configuration");
    let names = keys(system), user_off = false, overridden = false;
    let stock = ["name", "sysfs", "trigger", "dev", "mode", "default"];
    for (let i = 0; i < length(names); i++) {
        let section = system[names[i]];
        if (section[".type"] == "system") user_off = ("" + section.leds_off) == "1";
        if (section[".type"] != "led") continue;
        if (section.sysfs == "wan-error") overridden = true;
        if (section.sysfs != "wan") continue;
        let modes = type(section.mode) == "array" ? section.mode : split(trim(section.mode || ""), /\s+/);
        if (section.trigger != "netdev" || section.dev != "wan" ||
            join(" ", sort(modes)) != "link rx tx") overridden = true;
        let options = keys(section);
        for (let n = 0; n < length(options); n++) {
            if (substr(options[n], 0, 1) != "." && index(stock, options[n]) < 0)
                overridden = true;
        }
        if (section.default != null && section.default != "0" && section.default != "1")
            overridden = true;
    }
    return { user_off, overridden };
};

// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/col_wan_led_policy.uc</FILE> - <DESC>Normalize kernel link/default-route snapshots into the approved WAN indicator state.</DESC>
// <VERS>END OF VERSION: 0.1.2</VERS>
