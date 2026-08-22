// Generates a valid, importable n8n workflow JSON.
// Run once:
//   node build_workflow.js
//
// Output:
//   workflows/youtube-shorts-automation.json

const fs = require('fs');
const path = require('path');

// ============================================================
// GROQ SYSTEM PROMPT
// ============================================================

const systemPrompt = [
  "You are a viral YouTube Shorts scriptwriter.",
  "Create surprising, accurate and engaging 'Did you know?' Shorts.",
  "",
  "Return ONLY one valid JSON object.",
  "Do not use markdown.",
  "",
  "The JSON MUST contain exactly these keys:",
  "",
  "scenes - an array containing 5 to 7 scenes.",
  "",
  "Each scene MUST contain exactly:",
  "  text_en        - English narration for this scene.",
  "  text_ar        - accurate Arabic translation of the narration.",
  "  pexels_query   - 2 to 4 English words describing the visual.",
  "",
  "Also return:",
  "  hook        - a strong opening sentence.",
  "  script      - the complete English narration.",
  "  title       - curiosity-driven YouTube Shorts title ending with #Shorts.",
  "  description - 2 or 3 sentences followed by 5 relevant hashtags.",
  "  tags        - array of 8 to 12 lowercase keyword strings.",
  "",
  "IMPORTANT:",
  "- The complete narration should be 90 to 130 English words.",
  "- The hook must be the first scene's text_en.",
  "- The Arabic text must accurately translate each English scene.",
  "- Keep each scene short and natural for voice narration.",
  "- Use ONE surprising factual topic.",
  "- Facts must be scientifically or historically accurate.",
  "- No emojis.",
  "- No hashtags inside narration.",
  "- No stage directions.",
  "- Make the narration conversational and exciting.",
  "- End with a short question or follow-for-more style line.",
  "",
  "Vary topics between science, space, history, biology, psychology, technology and nature.",
  "",
  "The TTS voice is Kokoro af_bella.",
  "The narration MUST therefore be written in natural English."
].join("\n");

// ============================================================
// BUILD GROQ REQUEST
// ============================================================

const buildPromptCode = [
  "const system = " + JSON.stringify(systemPrompt) + ";",
  "",
  "const body = {",
  "  model: 'llama-3.3-70b-versatile',",
  "  temperature: 0.85,",
  "  response_format: { type: 'json_object' },",
  "  messages: [",
  "    {",
  "      role: 'system',",
  "      content: system",
  "    },",
  "    {",
  "      role: 'user',",
  "      content: 'Generate ONE fresh YouTube Short now. Return the JSON object only.'",
  "    }",
  "  ]",
  "};",
  "",
  "return [{ json: { body } }];"
].join("\n");

// ============================================================
// PARSE GROQ RESPONSE
// ============================================================

const parseScriptCode = [
  "const res = $input.first().json;",
  "",
  "const content =",
  "  res.choices &&",
  "  res.choices[0] &&",
  "  res.choices[0].message &&",
  "  res.choices[0].message.content;",
  "",
  "if (!content) {",
  "  throw new Error(",
  "    'Groq returned no content: ' +",
  "    JSON.stringify(res).slice(0, 1000)",
  "  );",
  "}",
  "",
  "let data;",
  "",
  "try {",
  "  data = JSON.parse(content);",
  "} catch (e) {",
  "  throw new Error(",
  "    'Groq returned invalid JSON: ' +",
  "    content.slice(0, 1000)",
  "  );",
  "}",
  "",
  "if (!data.scenes || !Array.isArray(data.scenes)) {",
  "  throw new Error('Groq JSON is missing scenes array.');",
  "}",
  "",
  "if (data.scenes.length < 4) {",
  "  throw new Error(",
  "    'Groq returned fewer than 4 scenes: ' +",
  "    data.scenes.length",
  "  );",
  "}",
  "",
  "for (const scene of data.scenes) {",
  "  if (!scene.text_en) {",
  "    throw new Error('Scene is missing text_en.');",
  "  }",
  "",
  "  if (!scene.text_ar) {",
  "    throw new Error('Scene is missing text_ar.');",
  "  }",
  "",
  "  if (!scene.pexels_query) {",
  "    scene.pexels_query = 'nature';",
  "  }",
  "}",
  "",
  "// Always use Kokoro Bella.",
  "data.voice = 'af_bella';",
  "",
  "data.title = data.title || 'Amazing Fact #Shorts';",
  "data.description = data.description || '';",
  "data.tags = Array.isArray(data.tags) ? data.tags : [];",
  "data.script = data.script || data.scenes.map(s => s.text_en).join(' ');",
  "",
  "return [{ json: data }];"
].join("\n");

// ============================================================
// BUILD JOB FOR produce.sh
// ============================================================

const buildJobCode = [
  "const item = $input.first().json;",
  "",
  "const runId = String($execution.id || Date.now());",
  "const runDir = `/data/${runId}`;",
  "",
  "const job = {",
  "  voice: 'af_bella',",
  "  scenes: item.scenes.map(scene => ({",
  "    text_en: String(scene.text_en || '').trim(),",
  "    text_ar: String(scene.text_ar || '').trim(),",
  "    pexels_query: String(scene.pexels_query || 'nature').trim()",
  "  }))",
  "};",
  "",
  "if (job.scenes.length < 4) {",
  "  throw new Error('Need at least 4 usable scenes.');",
  "}",
  "",
  "const jobB64 = Buffer",
  "  .from(JSON.stringify(job), 'utf8')",
  "  .toString('base64');",
  "",
  "return [{",
  "  json: {",
  "    runId,",
  "    runDir,",
  "    jobB64,",
  "    title: item.title,",
  "    description: item.description,",
  "    tags: item.tags,",
  "    voice: 'af_bella'",
  "  }",
  "}];"
].join("\n");

// ============================================================
// PRODUCE COMMAND
// ============================================================

const produceCommand =
  "mkdir -p {{ $json.runDir }} && " +
  "echo '{{ $json.jobB64 }}' | base64 -d > {{ $json.runDir }}/job.json && " +
  "/scripts/produce.sh {{ $json.runDir }}";

// ============================================================
// WORKFLOW
// ============================================================

const wf = {
  id: "shortsdidyouknow",
  name: "YouTube Shorts — Did You Know — Kokoro Bella",
  active: false,

  settings: {
    executionOrder: "v1"
  },

  nodes: [

    // --------------------------------------------------------
    // SCHEDULE
    // --------------------------------------------------------

    {
      parameters: {
        rule: {
          interval: [
            {
              field: "hours",
              triggerAtHour: 14
            }
          ]
        }
      },

      id: "node-schedule",

      name: "Daily Schedule",

      type: "n8n-nodes-base.scheduleTrigger",

      typeVersion: 1.2,

      position: [
        -80,
        300
      ]
    },

    // --------------------------------------------------------
    // BUILD GROQ REQUEST
    // --------------------------------------------------------

    {
      parameters: {
        jsCode: buildPromptCode
      },

      id: "node-buildprompt",

      name: "Build Prompt",

      type: "n8n-nodes-base.code",

      typeVersion: 2,

      position: [
        180,
        300
      ]
    },

    // --------------------------------------------------------
    // GROQ
    // --------------------------------------------------------

    {
      parameters: {

        method: "POST",

        url: "https://api.groq.com/openai/v1/chat/completions",

        sendHeaders: true,

        headerParameters: {
          parameters: [

            {
              name: "Authorization",

              value:
                "={{ 'Bearer ' + $env.GROQ_API_KEY }}"
            },

            {
              name: "Content-Type",

              value: "application/json"
            }

          ]
        },

        sendBody: true,

        specifyBody: "json",

        jsonBody: "={{ $json.body }}",

        options: {
          timeout: 60000
        }

      },

      id: "node-groq",

      name: "Generate Script (Groq)",

      type: "n8n-nodes-base.httpRequest",

      typeVersion: 4.2,

      position: [
        440,
        300
      ]
    },

    // --------------------------------------------------------
    // PARSE
    // --------------------------------------------------------

    {
      parameters: {
        jsCode: parseScriptCode
      },

      id: "node-parse",

      name: "Parse Script",

      type: "n8n-nodes-base.code",

      typeVersion: 2,

      position: [
        700,
        300
      ]
    },

    // --------------------------------------------------------
    // BUILD JOB
    // --------------------------------------------------------

    {
      parameters: {
        jsCode: buildJobCode
      },

      id: "node-buildjob",

      name: "Build Job",

      type: "n8n-nodes-base.code",

      typeVersion: 2,

      position: [
        960,
        300
      ]
    },

    // --------------------------------------------------------
    // PRODUCE VIDEO
    // --------------------------------------------------------

    {
      parameters: {
        command: "=" + produceCommand
      },

      id: "node-produce",

      name: "Produce Video",

      type: "n8n-nodes-base.executeCommand",

      typeVersion: 1,

      position: [
        1220,
        300
      ]
    },

    // --------------------------------------------------------
    // READ VIDEO
    // --------------------------------------------------------

    {
      parameters: {

        operation: "read",

        fileSelector:
          "={{ $('Build Job').item.json.runDir }}/video.mp4",

        options: {}

      },

      id: "node-readvideo",

      name: "Read Video File",

      type: "n8n-nodes-base.readWriteFile",

      typeVersion: 1,

      position: [
        1480,
        300
      ]
    },

    // --------------------------------------------------------
    // YOUTUBE
    // --------------------------------------------------------

    {
      parameters: {

        resource: "video",

        operation: "upload",

        title:
          "={{ $('Parse Script').item.json.title }}",

        categoryId: "27",

        binaryProperty: "data",

        options: {

          description:
            "={{ $('Parse Script').item.json.description }}",

          privacyStatus: "private",

          tags:
            "={{ ($('Parse Script').item.json.tags || []).join(',') }}"

        }

      },

      id: "node-youtube",

      name: "Upload to YouTube",

      type: "n8n-nodes-base.youTube",

      typeVersion: 1,

      position: [
        1740,
        300
      ],

      credentials: {

        youTubeOAuth2Api: {
          id: "REPLACE_ME",
          name: "YouTube account"
        }

      }
    }

  ],

  // ==========================================================
  // CONNECTIONS
  // ==========================================================

  connections: {

    "Daily Schedule": {
      main: [
        [
          {
            node: "Build Prompt",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Build Prompt": {
      main: [
        [
          {
            node: "Generate Script (Groq)",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Generate Script (Groq)": {
      main: [
        [
          {
            node: "Parse Script",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Parse Script": {
      main: [
        [
          {
            node: "Build Job",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Build Job": {
      main: [
        [
          {
            node: "Produce Video",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Produce Video": {
      main: [
        [
          {
            node: "Read Video File",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Read Video File": {
      main: [
        [
          {
            node: "Upload to YouTube",
            type: "main",
            index: 0
          }
        ]
      ]
    }

  },

  pinData: {}
};

// ============================================================
// WRITE WORKFLOW
// ============================================================

const outDir =
  path.join(
    __dirname,
    "workflows"
  );

fs.mkdirSync(
  outDir,
  {
    recursive: true
  }
);

const outPath =
  path.join(
    outDir,
    "youtube-shorts-automation.json"
  );

fs.writeFileSync(
  outPath,
  JSON.stringify(
    wf,
    null,
    2
  )
);

console.log(
  "Wrote:",
  outPath
);
