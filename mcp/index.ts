// mcp 依赖
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import {
    Tool,
    CallToolRequestSchema,
    ListToolsRequestSchema,
  } from '@modelcontextprotocol/sdk/types.js';

// 三方依赖
import express, { Request, Response } from 'express';
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";
import moment from "moment";
import fs from "fs";

const server = new Server(
    {
        name: "MediaCrawler MCP Server",
        version: "1.0.0",
    },
    {
        capabilities: {
        tools: {},
        logging: {},
        },
    }
);

// 认证逻辑
const AUTH_API_KEYS = ["alarm-mng-service-online", "test1"];

function getApiKey(req: Request) {
  // 支持 headers（区分大小写）、query、body
  return (
    req.headers["apikey"] ||
    req.headers["apiKey"] ||
    req.query.apiKey ||
    (req.body && req.body.apiKey)
  );
}

function validateApiKey(apiKey: any): boolean {
  if (!apiKey) return false;
  return AUTH_API_KEYS.includes(String(apiKey));
}

const RUN_CRAWLER_TOOL: Tool = {
    name: "runCrawler",
    description: "调用 main.py，支持 platform/lt/type/keywords 等参数",
    inputSchema: {
      type: "object",
      properties: {
        platform: {
          type: "string",
          description: "平台标识，可选"
        },
        lt: {
          type: "string",
          description: "lt参数，可选",
          default: ""
        },
        type: {
          type: "string",
          description: "类型参数，可选",
          default: ""
        },
        start: {
          type: "string",
          description: "起始参数，可选",
          default: ""
        },
        keywords: {
          type: "string",
          description: "关键词，可选",
          default: ""
        },
        get_comment: {
          type: "boolean",
          description: "是否获取评论，默认false",
          default: false
        },
        get_sub_comment: {
          type: "boolean",
          description: "是否获取子评论，默认false",
          default: false
        },
        cookies: {
          type: "string",
          description: "cookies字符串，可选",
          default: ""
        },
        creator_id_list: {
          type: "string",
          description: "创作者ID列表，可选",
          default: ""
        },
        specified_id_list: {
          type: "string",
          description: "指定ID列表，可选",
          default: ""
        },
        crawler_max_notes_count: {
          type: "string",
          description: "爬取视频/帖子的数量控制，默认10",
          default: "10"
        },
        headless: {
          type: "boolean",
          description: "是否headless模式，默认true",
          default: true
        }
      },
      required: [],
      additionalProperties: false
    }
}

// Tool handlers
server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [
        RUN_CRAWLER_TOOL
    ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    switch (name) {
        case 'runCrawler': {
            return await runCrawler(args)
        }
        default: {
            return {content: [{ type: 'text', text: `Unknown tool: ${name}`},],isError: true,};
        }
    }
});

async function runCrawler(args) {
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);
    console.log('[runCrawler] 输入参数:', args);
    // 参数校验
    if (!args.platform || args.platform.trim() === '') {
      throw new Error('platform 不能为空');
    }
    if (!args.type || args.type.trim() === '') {
      throw new Error('type 不能为空');
    }
    if (args.type === 'detail' && (!args.specified_id_list || args.specified_id_list.trim() === '')) {
      throw new Error('type=detail 时，必须传入 specified_id_list');
    }
    if (args.type === 'creator' && (!args.creator_id_list || args.creator_id_list.trim() === '')) {
      throw new Error('type=creator 时，必须传入 creator_id_list');
    }
    if (args.type === 'search' && (!args.keywords || args.keywords.trim() === '')) {
      throw new Error('type=search 时，必须传入 keywords');
    }
    // 参数转为命令行
    const argMap = {
      platform: "--platform",
      lt: "--lt",
      type: "--type",
      start: "--start",
      keywords: "--keywords",
      get_comment: "--get_comment",
      get_sub_comment: "--get_sub_comment",
      cookies: "--cookies",
      creator_id_list: "--creator_id_list",
      specified_id_list: "--specified_id_list",
      crawler_max_notes_count: "--crawler_max_notes_count",
      headless: "--headless",
    };
    const pyArgs: string[] = [];
    // 1. 生成文件名 file_${datetime}，格式yyyymmddhh24miss
    function getCurrentDateTimeStr() {
      return moment().format("YYYYMMDDHHmmss");
    }
    // 始终自动生成文件名
    const saveFileTimestamp = `${getCurrentDateTimeStr()}`;
    // 组装参数时，自动加上 --save_file_timestamp
    for (const [k, v] of Object.entries(args)) {
      if (v !== undefined && v !== null && v !== "") {
        pyArgs.push(argMap[k as keyof typeof argMap]);
        pyArgs.push(String(v));
      }
    }
    pyArgs.push("--save_file_timestamp");
    pyArgs.push(saveFileTimestamp);
    const pyPath = path.resolve(__dirname, "../main.py");
    const pythonCmd = "uv";
    const pyArgsFull = ["run", pyPath, ...pyArgs];
    const fullCmd = [pythonCmd, ...pyArgsFull].join(" ");
    console.log(`[runCrawler] 执行命令: ${fullCmd}`);
    return new Promise((resolve) => {
      const child = spawn(pythonCmd, pyArgsFull, { cwd: path.resolve(__dirname, "..") });
      let output = "";
      let error = "";
      child.stdout.on("data", (data) => {
        output += data.toString();
        process.stdout.write(`[runCrawler][stdout] ${data}`);
      });
      child.stderr.on("data", (data) => {
        error += data.toString();
        process.stderr.write(`[runCrawler][stderr] ${data}`);
      });
      child.on("close", async (code) => {
        console.log(`[runCrawler] 子进程退出，code=${code}`);
        let platformDir = args.platform || 'xhs';
        const jsonDir = path.resolve(__dirname, `../data/${platformDir}/json/`);
        if (code === 0) {
          try {
            // 读取 jsonDir 下所有包含 saveFileTimestamp 的文件
            const files = await fs.promises.readdir(jsonDir);
            const matchedFiles = files.filter(f => f.includes(saveFileTimestamp));
            console.log(`[runCrawler] 匹配到的文件:`, matchedFiles);
            if (matchedFiles.length === 0) {
              resolve({ content: [{ type: "text", text: `命令: ${fullCmd}\n未找到包含 ${saveFileTimestamp} 的文件。` }], isError: true });
              return;
            }
            const result: Record<string, any> = {};
            for (const file of matchedFiles) {
              const filePath = path.join(jsonDir, file);
              try {
                const fileContent = await fs.promises.readFile(filePath, 'utf-8');
                result[file] = JSON.parse(fileContent);
                console.log(`[runCrawler] 读取并解析文件: ${filePath}`);
              } catch (e) {
                result[file] = { error: `读取或解析失败: ${e}` };
                console.error(`[runCrawler] 读取或解析失败: ${filePath}`, e);
              }
              console.log('runCrawler result:',result)
            }
            resolve({
              content: [
                { type: "text", text: `${JSON.stringify(result, null, 2)}` }
              ],
              isError: false
            });
            return;
          } catch (e) {
            console.error(`[runCrawler] 文件读取失败:`, e);
            resolve({ content: [{ type: "text", text: `命令: ${fullCmd}\n文件读取失败: ${e}` }], isError: true });
            return;
          }
        } else {
          console.error(`[runCrawler] 子进程异常退出，error:`, error, output);
          resolve({ content: [{ type: "text", text: `命令: ${fullCmd}\nError: ${error}\n${output}` }], isError: true });
          return;
        }
      });
    });
}

async function runSSELocalServer() {
    let transport: SSEServerTransport | null = null;
    const app = express();
  
    app.get('/sse', async (req, res) => {
      transport = new SSEServerTransport(`/messages`, res);
      res.on('close', () => {
        transport = null;
      });
      await server.connect(transport);
    });
  
    // Endpoint for the client to POST messages
    // Remove express.json() middleware - let the transport handle the body
    app.post('/messages', (req, res) => {
      if (transport) {
        transport.handlePostMessage(req, res);
      }
    });
  
    // 支持 PORT 环境变量，默认为 3000
    const PORT = process.env.PORT || 3000;
    console.log('Starting server on port', PORT);
    try {
      app.listen(PORT, () => {
        console.log(`MCP SSE Server listening on http://localhost:${PORT}`);
        console.log(`SSE endpoint: http://localhost:${PORT}/sse`);
        console.log(`Message endpoint: http://localhost:${PORT}/messages`);
      });
    } catch (error) {
      console.error('Error starting server:', error);
    }
  }

  async function runSSECloudServer() {
    const transports: { [sessionId: string]: SSEServerTransport } = {};
    const app = express();
  
    app.get('/health', (req, res) => {
      res.status(200).send('OK');
    });
  
    app.get('/sse', async (req, res) => {
      const apiKey = getApiKey(req);
      // 校验 apiKey
      if (!validateApiKey(apiKey)) {
        res.status(401).json({ error: "Unauthorized: Invalid apiKey" });
        res.end();
        return;
      }
      const transport = new SSEServerTransport(`/messages`, res);
      const compositeKey = `${apiKey}-${transport.sessionId}`;
      transports[compositeKey] = transport;
      res.on('close', () => {
        delete transports[compositeKey];
      });
      await server.connect(transport);
    });
  
    // Endpoint for the client to POST messages
    // Remove express.json() middleware - let the transport handle the body
    app.post(
      '/messages',
      express.json(),
      async (req: Request, res: Response) => {
        const apiKey = getApiKey(req);
        // 校验 apiKey
        if (!validateApiKey(apiKey)) {
          res.status(401).json({ error: "Unauthorized: Invalid apiKey" });
          res.end();
          return;
        }
        const body = req.body;
        const enrichedBody = {
          ...body,
        };
  
        console.log('enrichedBody', enrichedBody);
  
        const sessionId = req.query.sessionId as string;
        const compositeKey = `${apiKey}-${sessionId}`;
        const transport = transports[compositeKey];
        if (transport) {
          await transport.handlePostMessage(req, res, enrichedBody);
        } else {
          res.status(400).send('No transport found for sessionId');
        }
      }
    );
  
    // 支持 PORT 环境变量，默认为 3000
    const PORT = process.env.PORT || 3000;
    app.listen(PORT, () => {
      console.log(`MCP SSE Server listening on http://localhost:${PORT}`);
      console.log(`SSE endpoint: http://localhost:${PORT}/sse`);
      console.log(`Message endpoint: http://localhost:${PORT}/messages`);
    });
  }
  
if (process.env.CLOUD_SERVICE === 'true') {
    runSSECloudServer().catch((error: any) => {
        console.error('Fatal error running server:', error);
        process.exit(1);
    });
} else if (process.env.SSE_LOCAL === 'true') {
    runSSELocalServer().catch((error: any) => {
        console.error('Fatal error running server:', error);
        process.exit(1);
    });
}
  