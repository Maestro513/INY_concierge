#!/usr/bin/env node

/**
 * stitch-mcp - Patched MCP Server for Google Stitch
 * Uses STITCH_API_KEY instead of gcloud OAuth
 */

const { Server } = require("@modelcontextprotocol/sdk/server/index.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const fs = require("fs");
const path = require("path");
const os = require("os");
const fetch = require("node-fetch");

const STITCH_URL = "https://stitch.googleapis.com/mcp";
const TIMEOUT_MS = 180000;

const log = {
    info: (msg) => console.error(`[stitch-mcp] ℹ️  ${msg}`),
    success: (msg) => console.error(`[stitch-mcp] ✅ ${msg}`),
    warn: (msg) => console.error(`[stitch-mcp] ⚠️  ${msg}`),
    error: (msg) => console.error(`[stitch-mcp] ❌ ${msg}`),
};

function getAccessToken() {
    const key = process.env.STITCH_API_KEY;
    if (!key) throw new Error("STITCH_API_KEY environment variable is required");
    return key;
}

function getProjectId() {
    if (process.env.GOOGLE_CLOUD_PROJECT) return process.env.GOOGLE_CLOUD_PROJECT;
    if (process.env.GCLOUD_PROJECT) return process.env.GCLOUD_PROJECT;
    // Default project ID - Stitch may not strictly need one with API key auth
    return "stitch-default";
}

async function callStitchAPI(method, params, projectId) {
    const token = getAccessToken();

    const body = {
        jsonrpc: "2.0",
        method,
        params,
        id: Date.now()
    };

    log.info(`→ ${method}`);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
        const response = await fetch(STITCH_URL, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "X-Goog-User-Project": projectId,
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body),
            signal: controller.signal
        });

        clearTimeout(timeout);

        if (!response.ok) {
            const text = await response.text();
            let errorMessage = `HTTP ${response.status}: ${text}`;
            let errorCode = -32000;
            if (response.status === 400) errorCode = -32602;
            if (response.status === 401 || response.status === 403) errorCode = -32001;
            if (response.status === 404) errorCode = -32601;
            throw { code: errorCode, message: errorMessage };
        }

        const data = await response.json();
        log.success(`Completed ${method}`);
        return data;

    } catch (error) {
        clearTimeout(timeout);
        if (error.name === 'AbortError') throw { code: -32002, message: "Request timeout (3 minutes)" };
        if (error.code) throw error;
        throw { code: -32603, message: error.message || "Internal error" };
    }
}

function sanitizeSchema(obj) {
    if (!obj || typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) return obj.map(item => sanitizeSchema(item));
    const cleaned = {};
    for (const key of Object.keys(obj)) {
        if (key.startsWith('x-')) continue;
        cleaned[key] = sanitizeSchema(obj[key]);
    }
    return cleaned;
}

async function main() {
    try {
        log.info(`Starting Stitch MCP Server (patched) v1.0.0 (${os.platform()})`);

        const projectId = getProjectId();
        log.info(`Project: ${projectId}`);

        // Verify token exists
        getAccessToken();
        log.success("API key configured");

        const server = new Server(
            { name: "stitch", version: "1.0.0" },
            { capabilities: { tools: {} } }
        );

        const { ListToolsRequestSchema, CallToolRequestSchema } = require("@modelcontextprotocol/sdk/types.js");

        let cachedTools = null;

        const CUSTOM_TOOLS = [
            {
                name: "fetch_screen_code",
                description: "Retrieves the actual HTML/Code content of a screen.",
                inputSchema: {
                    type: "object",
                    properties: {
                        projectId: { type: "string", description: "The project ID" },
                        screenId: { type: "string", description: "The screen ID" }
                    },
                    required: ["projectId", "screenId"]
                }
            },
            {
                name: "fetch_screen_image",
                description: "Retrieves the screenshot/preview image of a screen.",
                inputSchema: {
                    type: "object",
                    properties: {
                        projectId: { type: "string", description: "The project ID" },
                        screenId: { type: "string", description: "The screen ID" }
                    },
                    required: ["projectId", "screenId"]
                }
            }
        ];

        server.setRequestHandler(ListToolsRequestSchema, async () => {
            try {
                const result = await callStitchAPI("tools/list", {}, projectId);
                const rawTools = result.result ? result.result.tools : [];
                const tools = rawTools.map(tool => ({
                    ...tool,
                    inputSchema: tool.inputSchema ? sanitizeSchema(tool.inputSchema) : tool.inputSchema
                }));
                return { tools: [...tools, ...CUSTOM_TOOLS] };
            } catch (error) {
                log.error(`Tools list failed: ${error.message}`);
                return { tools: [...CUSTOM_TOOLS] };
            }
        });

        server.setRequestHandler(CallToolRequestSchema, async (request) => {
            const { name, arguments: args } = request.params;

            if (name === "fetch_screen_code") {
                try {
                    log.info(`Fetching code for screen: ${args.screenId}`);
                    const screenRes = await callStitchAPI("tools/call", {
                        name: "get_screen",
                        arguments: { projectId: args.projectId, screenId: args.screenId }
                    }, projectId);
                    if (!screenRes.result) throw new Error("Could not fetch screen details");
                    let downloadUrl = null;
                    const findUrl = (obj) => {
                        if (downloadUrl) return;
                        if (!obj || typeof obj !== 'object') return;
                        if (obj.downloadUrl) { downloadUrl = obj.downloadUrl; return; }
                        for (const key in obj) findUrl(obj[key]);
                    };
                    findUrl(screenRes.result);
                    if (!downloadUrl) return { content: [{ type: "text", text: "No code download URL found." }], isError: true };
                    const res = await fetch(downloadUrl);
                    if (!res.ok) throw new Error(`Failed to download: ${res.status}`);
                    const code = await res.text();
                    return { content: [{ type: "text", text: code }] };
                } catch (err) {
                    return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
                }
            }

            if (name === "fetch_screen_image") {
                try {
                    log.info(`Fetching image for screen: ${args.screenId}`);
                    const screenRes = await callStitchAPI("tools/call", {
                        name: "get_screen",
                        arguments: { projectId: args.projectId, screenId: args.screenId }
                    }, projectId);
                    if (!screenRes.result) throw new Error("Could not fetch screen details");
                    let imageUrl = null;
                    const findImg = (obj) => {
                        if (imageUrl) return;
                        if (!obj || typeof obj !== 'object') return;
                        if (obj.screenshot && obj.screenshot.downloadUrl) { imageUrl = obj.screenshot.downloadUrl; return; }
                        const isImgUrl = (s) => typeof s === "string" && (s.includes(".png") || s.includes(".jpg") || (s.includes("googleusercontent.com") && !s.includes("contribution.usercontent")));
                        if (obj.downloadUrl && isImgUrl(obj.downloadUrl)) { imageUrl = obj.downloadUrl; return; }
                        if (obj.uri && isImgUrl(obj.uri)) { imageUrl = obj.uri; return; }
                        if (obj.name && (obj.name.includes("png") || obj.name.includes("jpg")) && obj.downloadUrl) { imageUrl = obj.downloadUrl; return; }
                        for (const key in obj) findImg(obj[key]);
                    };
                    findImg(screenRes.result);
                    if (!imageUrl) return { content: [{ type: "text", text: "No image URL found." }], isError: true };
                    log.info(`Downloading image from: ${imageUrl}`);
                    const imgRes = await fetch(imageUrl);
                    if (!imgRes.ok) throw new Error(`Failed to download image: ${imgRes.status}`);
                    const arrayBuffer = await imgRes.arrayBuffer();
                    const buffer = Buffer.from(arrayBuffer);
                    const fileName = `screen_${args.screenId}.png`;
                    const filePath = path.join(process.cwd(), fileName);
                    fs.writeFileSync(filePath, buffer);
                    log.info(`Saved image to: ${filePath}`);
                    const base64Img = buffer.toString('base64');
                    return {
                        content: [
                            { type: "text", text: `Image saved to ${fileName}` },
                            { type: "image", data: base64Img, mimeType: "image/png" }
                        ]
                    };
                } catch (err) {
                    return { content: [{ type: "text", text: `Error: ${err.message}` }], isError: true };
                }
            }

            try {
                const result = await callStitchAPI("tools/call", { name, arguments: args || {} }, projectId);
                if (result.result) {
                    try {
                        const processObject = async (obj) => {
                            if (!obj || typeof obj !== 'object') return;
                            if (obj.downloadUrl && typeof obj.downloadUrl === 'string') {
                                try {
                                    log.info(`Auto-downloading content from: ${obj.downloadUrl.substring(0, 50)}...`);
                                    const res = await fetch(obj.downloadUrl);
                                    if (res.ok) { obj.content = await res.text(); log.success("Content downloaded!"); }
                                } catch (err) { log.error(`Download error: ${err.message}`); }
                            }
                            for (const key in obj) await processObject(obj[key]);
                        };
                        await processObject(result.result);
                    } catch (e) { log.error(`Processing failed: ${e.message}`); }
                }
                if (result.result) {
                    if (result.result.content && Array.isArray(result.result.content)) return result.result;
                    return { content: [{ type: "text", text: JSON.stringify(result.result, null, 2) }] };
                }
                if (result.error) return { content: [{ type: "text", text: `API Error: ${result.error.message}` }], isError: true };
                return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
            } catch (error) {
                log.error(`Tool ${name} failed: ${error.message}`);
                return { content: [{ type: "text", text: `Error: ${error.message}` }], isError: true };
            }
        });

        server.onerror = (err) => log.error(`Server error: ${err}`);

        const transport = new StdioServerTransport();
        await server.connect(transport);
        log.success("Server ready and listening on stdio");

    } catch (error) {
        log.error(`Fatal Startup Error: ${error.message}`);
        process.exit(1);
    }
}

main();
