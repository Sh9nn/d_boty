const WebSocket = require("ws");
const fs = require("fs");

const PORT = process.env.PORT || 8080;
const KEYS_FILE = "keys.json";

function loadKeys() {
    if (!fs.existsSync(KEYS_FILE)) return {};
    return JSON.parse(fs.readFileSync(KEYS_FILE, "utf-8"));
}

function saveKeys(keys) {
    fs.writeFileSync(KEYS_FILE, JSON.stringify(keys, null, 4), "utf-8");
}

function checkKey(key, hwid) {
    const keys = loadKeys();

    for (const userId in keys) {
        const data = keys[userId];

        if (data.key !== key) continue;

        // Проверка срока
        if (data.expiry !== "lifetime") {
            const expiry = new Date(data.expiry);
            if (new Date() > expiry) {
                return { status: "expired" };
            }
        }

        // Привязка HWID
        if (!data.hwid) {
            data.hwid = hwid;
            keys[userId] = data;
            saveKeys(keys);
            return { status: "ok", user: data.username };
        }

        if (data.hwid === hwid) {
            return { status: "ok", user: data.username };
        } else {
            return { status: "hwid_mismatch" };
        }
    }

    return { status: "invalid" };
}

const wss = new WebSocket.Server({ port: PORT });

wss.on("listening", () => {
    console.log(`WebSocket server started on port ${PORT}`);
});

wss.on("connection", (ws) => {
    ws.on("message", (message) => {
        try {
            const data = JSON.parse(message);
            const key = (data.key || "").trim();
            const hwid = (data.hwid || "").trim();

            if (!key || !hwid) {
                ws.send(JSON.stringify({ status: "invalid" }));
                return;
            }

            const result = checkKey(key, hwid);
            ws.send(JSON.stringify(result));
        } catch {
            ws.send(JSON.stringify({ status: "invalid" }));
        }
    });
});
