// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_wan_led_runtime_path.uc</FILE> - <DESC>Validate private root-owned RAM parents before WAN policy runtime writes.</DESC>
// <VERS>VERSION: 0.1.0</VERS>
// <WCTX>Prevent predictable lock and status paths from following untrusted temporary-file links.</WCTX>
// <CLOG>Validate canonical ancestors and private parents without changing existing permissions or dry-run state.</CLOG>

export function wan_led_runtime_path(fs, path, dry_run) {
    if (type(path) != "string" || substr(path, 0, 5) != "/tmp/" || match(path, /[\r\n]/))
        die("WAN runtime path must be under /tmp");
    let parts = split(path, "/"), parent = fs.dirname(path), current = "";
    if (length(parts) < 4) die("WAN runtime path needs a private parent");
    for (let i = 1; i < length(parts); i++) {
        if (parts[i] == "" || parts[i] == "." || parts[i] == "..")
            die("WAN runtime path must be normalized");
    }
    for (let i = 1; i < length(parts) - 1; i++) {
        current += "/" + parts[i];
        let info = fs.lstat(current);
        if (!info) {
            if (current != parent) die("WAN runtime ancestor is missing: " + current);
            let ancestor = fs.dirname(current);
            if (fs.realpath(ancestor) != ancestor)
                die("WAN runtime ancestor is not canonical");
            if (dry_run) return path;
            fs.mkdir(current, 448); // 0700; validate after creation, including an EEXIST race.
            info = fs.lstat(current);
        }
        if (!info || info.type != "directory" || info.uid != 0 || type(info.mode) != "int")
            die("WAN runtime parent is not a root-owned directory: " + current);
        if (fs.realpath(current) != current)
            die("WAN runtime parent traverses a symlink: " + current);
        if (current == "/tmp") {
            if ((info.mode & 18) && !(info.mode & 512)) die("Writable /tmp must be sticky");
        }
        else if ((info.mode & 18) || (current == parent && (info.mode & 4095) != 448))
            die("WAN runtime parent is not private: " + current);
    }
    let leaf = fs.lstat(path);
    if (leaf && (leaf.type != "file" || leaf.uid != 0 || (leaf.mode & 18)))
        die("WAN runtime file is not trusted: " + path);
    return path;
};

// <FILE>target/linux/bcm4908/base-files/usr/share/ac86u/fnc_wan_led_runtime_path.uc</FILE> - <DESC>Validate private root-owned RAM parents before WAN policy runtime writes.</DESC>
// <VERS>END OF VERSION: 0.1.0</VERS>
