import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { spawn } from "child_process";
import path from "path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "url";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import moment from "moment";
import fs from "fs";
import express from "express";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// @ts-ignore
// eslint-disable-next-line
declare var process: NodeJS.Process;

// 1. 创建 MCP Server
const sessionFileMap = new Map();
const server = new McpServer({
  name: "MediaCrawler MCP Server",
  version: "1.0.0",
});

// 2. 注册 runCrawler 工具
server.registerTool(
  "runCrawler",
  {
    title: "运行 MediaCrawler 爬虫",
    description: "调用 main.py，支持 platform/lt/type/keywords 等参数",
    inputSchema: {
      platform: z.string().optional(),
      lt: z.string().optional(),
      type: z.string().optional(),
      start: z.number().optional(),
      keywords: z.string().optional(),
      get_comment: z.boolean().optional().default(false),
      get_sub_comment: z.boolean().optional().default(false),
      cookies: z.string().optional(),
      creator_id_list: z.string().optional(),
      specified_id_list: z.string().optional(),
      headless: z.boolean().optional().default(true),
    },
  },
  async (args, session) => {
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
              // console.log(result)
            }
            resolve({
              content: [
                { type: "text", text: `${JSON.stringify(result, null, 2)}` }
              ]
            });
          } catch (e) {
            console.error(`[runCrawler] 文件读取失败:`, e);
            resolve({ content: [{ type: "text", text: `命令: ${fullCmd}\n文件读取失败: ${e}` }], isError: true });
          }
        } else {
          console.error(`[runCrawler] 子进程异常退出，error:`, error, output);
          resolve({ content: [{ type: "text", text: `命令: ${fullCmd}\nError: ${error}\n${output}` }], isError: true });
        }
      });
    });
  }
);

// 3. 启动 MCP HTTP/SSE 服务
const app = express();
app.use(express.json());

const transport = new StreamableHTTPServerTransport({
  sessionIdGenerator: () => randomUUID(),
});

// POST: 客户端请求
app.post('/mcp', async (req, res) => {
  console.error('mcp post:', req.body)
  await transport.handleRequest(req, res, req.body);
});
// GET: SSE 事件流
app.get('/mcp', async (req, res) => {
  console.error('mcp get:', req.body)
  await transport.handleRequest(req, res);
});
// DELETE: 关闭 session
app.delete('/mcp', async (req, res) => {
  await transport.handleRequest(req, res);
});

const PORT = 3000;
server.connect(transport).then(() => {
  app.listen(PORT, () => {
    console.error(`MCP server running (HTTP/SSE) on port ${PORT}...`);
  });
});

// const transport = new StdioServerTransport();
// (async () => {
//   await server.connect(transport)
//     .then(() => {
//       // console.error("MCP stdio running (HTTP)...");
//     })
//     .catch((err) => {
//       console.error("Failed to start MCP stdio:", err);
//     });
// })(); 