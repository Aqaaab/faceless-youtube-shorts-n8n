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
  "You are an expert viral YouTube Shorts scriptwriter.",
  "Create ONE surprising, accurate and engaging 'Did you know?' YouTube Short.",
  "",
  "CRITICAL LANGUAGE RULE:",
  "text_en MUST contain ENGLISH ONLY.",
  "text_ar MUST contain ARABIC ONLY as a translation of text_en.",
  "NEVER put Arabic inside text_en.",
  "NEVER put English narration inside text_ar.",
  "",
  "Return ONLY one valid JSON object.",
  "Do not use markdown.",
  "Do not use code fences.",
  "",
  "The JSON MUST contain exactly these top-level keys:",
  "",
  "scenes",
  "hook",
  "script",
  "title",
  "description",
  "tags",
  "",
  "scenes MUST contain 5 to 7 scene objects.",
  "",
  "Each scene MUST contain exactly these keys:",
  "text_en",
  "text_ar",
  "pexels_query",
  "",
  "SCENE RULES:",
  "- text_en: natural spoken American English.",
  "- text_ar: accurate Modern Standard Arabic translation.",
  "- pexels_query: 2 to 4 English words describing the visual.",
  "- Every scene must add new information.",
  "- Do not repeat sentences or facts between scenes.",
  "- Keep scenes short and natural for TTS.",
  "",
  "CONTENT RULES:",
  "- Use ONE surprising factual topic.",
  "- Facts must be scientifically or historically accurate.",
  "- Do not invent facts.",
  "- No emojis.",
  "- No hashtags inside narration.",
  "- No stage directions.",
  "- No quotation marks around the narration.",
  "- Make the narration conversational and exciting.",
  "- End with a short question or follow-for-more style line.",
  "",
  "LENGTH RULE:",
  "- The complete English narration must contain 90 to 130 English words.",
  "- script must be the complete English narration.",
  "- script must equal the scenes' text_en joined with spaces.",
  "- hook MUST equal scenes[0].text_en exactly.",
  "",
  "TITLE RULE:",
  "- Curiosity-driven.",
  "- English.",
  "- Must end with #Shorts.",
  "",
  "DESCRIPTION RULE:",
  "- 2 or 3 short English sentences.",
  "- Then exactly 5 relevant hashtags.",
  "",
  "TAGS RULE:",
  "- Array of 8 to 12 lowercase English keyword strings.",
  "",
  "TOPIC VARIATION:",
  "Vary topics between science, space, history, biology, psychology, technology and nature.",
  "",
  "TTS:",
  "The voice is Kokoro af_bella.",
  "The English narration must therefore sound natural when spoken aloud.",
  "",
  "IMPORTANT:",
  "The first scene is the hook.",
  "Do not translate the English into Arabic incorrectly.",
  "Do not output Arabic characters anywhere inside text_en, hook, script, title, description or tags."
].join("\n");

// ============================================================
// BUILD GROQ REQUEST
// ============================================================

const buildPromptCode = [
  "const system = " + JSON.stringify(systemPrompt) + ";",
  "",
  "const topics = [",
  "  'science',",
  "  'space',",
  "  'history',",
  "  'biology',",
  "  'psychology',",
  "  'technology',",
  "  'nature'",
  "];",
  "",
  "const topic = topics[Math.floor(Math.random() * topics.length)];",
  "",
  "const body = {",
  "  model: 'llama-3.3-70b-versatile',",
  "  temperature: 0.75,",
  "  max_tokens: 1200,",
  "  response_format: { type: 'json_object' },",
  "  messages: [",
  "    {",
  "      role: 'system',",
  "      content: system",
  "    },",
  "    {",
  "      role: 'user',",
  "      content:",
  "        'Generate ONE fresh YouTube Short about the topic category: ' +",
  "        topic +",
  "        '. Return the JSON object only. English narration must be English only.'",
  "    }",
  "  ]",
  "};",
  "",
  "return [{ json: { body } }];"
].join("\n");

// ============================================================
// PARSE + VALIDATE GROQ RESPONSE
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
  "    JSON.stringify(res).slice(0, 1500)",
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
  "    content.slice(0, 1500)",
  "  );",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Helpers",
  "// ----------------------------------------------------------",
  "",
  "function hasArabic(text) {",
  "  return /[\\u0600-\\u06FF]/.test(String(text || ''));",
  "}",
  "",
  "function hasEnglishLetters(text) {",
  "  return /[A-Za-z]/.test(String(text || ''));",
  "}",
  "",
  "function englishOnly(text) {",
  "  const value = String(text || '');",
  "  return hasEnglishLetters(value) && !hasArabic(value);",
  "}",
  "",
  "function wordCount(text) {",
  "  return String(text || '')",
  "    .trim()",
  "    .split(/\\s+/)",
  "    .filter(Boolean)",
  "    .length;",
  "}",
  "",
  "function normalize(text) {",
  "  return String(text || '')",
  "    .toLowerCase()",
  "    .replace(/[^a-z0-9\\u0600-\\u06FF]+/g, ' ')",
  "    .replace(/\\s+/g, ' ')",
  "    .trim();",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Required structure",
  "// ----------------------------------------------------------",
  "",
  "if (!data || typeof data !== 'object') {",
  "  throw new Error('Groq response is not an object.');",
  "}",
  "",
  "if (!Array.isArray(data.scenes)) {",
  "  throw new Error('Groq JSON is missing scenes array.');",
  "}",
  "",
  "if (data.scenes.length < 5 || data.scenes.length > 7) {",
  "  throw new Error(",
  "    'Groq must return 5 to 7 scenes. Got: ' +",
  "    data.scenes.length",
  "  );",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Validate scenes",
  "// ----------------------------------------------------------",
  "",
  "const seenEnglish = new Set();",
  "",
  "for (let i = 0; i < data.scenes.length; i++) {",
  "  const scene = data.scenes[i];",
  "",
  "  if (!scene || typeof scene !== 'object') {",
  "    throw new Error('Scene ' + (i + 1) + ' is invalid.');",
  "  }",
  "",
  "  if (!scene.text_en) {",
  "    throw new Error('Scene ' + (i + 1) + ' is missing text_en.');",
  "  }",
  "",
  "  if (!scene.text_ar) {",
  "    throw new Error('Scene ' + (i + 1) + ' is missing text_ar.');",
  "  }",
  "",
  "  if (!scene.pexels_query) {",
  "    throw new Error(",
  "      'Scene ' + (i + 1) + ' is missing pexels_query.'",
  "    );",
  "  }",
  "",
  "  scene.text_en = String(scene.text_en).trim();",
  "  scene.text_ar = String(scene.text_ar).trim();",
  "  scene.pexels_query = String(scene.pexels_query).trim();",
  "",
  "  if (!englishOnly(scene.text_en)) {",
  "    throw new Error(",
  "      'LANGUAGE ERROR: Scene ' +",
  "      (i + 1) +",
  "      ' text_en is not English-only: ' +",
  "      scene.text_en.slice(0, 250)",
  "    );",
  "  }",
  "",
  "  if (!hasArabic(scene.text_ar)) {",
  "    throw new Error(",
  "      'LANGUAGE ERROR: Scene ' +",
  "      (i + 1) +",
  "      ' text_ar does not contain Arabic.'",
  "    );",
  "  }",
  "",
  "  const normalized = normalize(scene.text_en);",
  "",
  "  if (seenEnglish.has(normalized)) {",
  "    throw new Error(",
  "      'DUPLICATE ERROR: Scene ' +",
  "      (i + 1) +",
  "      ' repeats an earlier scene.'",
  "    );",
  "  }",
  "",
  "  seenEnglish.add(normalized);",
  "",
  "  const queryWords = scene.pexels_query",
  "    .split(/\\s+/)",
  "    .filter(Boolean);",
  "",
  "  if (queryWords.length < 2 || queryWords.length > 4) {",
  "    throw new Error(",
  "      'Pexels query for scene ' +",
  "      (i + 1) +",
  "      ' must contain 2 to 4 English words.'",
  "    );",
  "  }",
  "",
  "  if (!englishOnly(scene.pexels_query)) {",
  "    throw new Error(",
  "      'Pexels query for scene ' +",
  "      (i + 1) +",
  "      ' must be English.'",
  "    );",
  "  }",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Build/validate complete script",
  "// ----------------------------------------------------------",
  "",
  "const generatedScript = data.scenes",
  "  .map(scene => scene.text_en)",
  "  .join(' ')",
  "  .trim();",
  "",
  "if (!englishOnly(generatedScript)) {",
  "  throw new Error('Final narration contains non-English text.');",
  "}",
  "",
  "const words = wordCount(generatedScript);",
  "",
  "if (words < 90 || words > 130) {",
  "  throw new Error(",
  "    'Narration must contain 90-130 English words. Got: ' +",
  "    words",
  "  );",
  "}",
  "",
  "data.script = generatedScript;",
  "",
  "data.hook = String(data.hook || '').trim();",
  "",
  "if (!data.hook) {",
  "  data.hook = data.scenes[0].text_en;",
  "}",
  "",
  "if (data.hook !== data.scenes[0].text_en) {",
  "  throw new Error(",
  "    'Hook must exactly equal the first scene text_en.'",
  "  );",
  "}",
  "",
  "if (!englishOnly(data.hook)) {",
  "  throw new Error('Hook contains non-English text.');",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Metadata validation",
  "// ----------------------------------------------------------",
  "",
  "data.title = String(",
  "  data.title || 'Amazing Fact #Shorts'",
  ").trim();",
  "",
  "if (!englishOnly(data.title)) {",
  "  throw new Error('Title must be English.');",
  "}",
  "",
  "if (!data.title.endsWith('#Shorts')) {",
  "  data.title = data.title.replace(/\\s+$/g, '') + ' #Shorts';",
  "}",
  "",
  "data.description = String(data.description || '').trim();",
  "",
  "if (!englishOnly(data.description)) {",
  "  throw new Error('Description must be English.');",
  "}",
  "",
  "if (!Array.isArray(data.tags)) {",
  "  data.tags = [];",
  "}",
  "",
  "data.tags = data.tags",
  "  .map(tag => String(tag || '').trim().toLowerCase())",
  "  .filter(Boolean);",
  "",
  "if (data.tags.length < 8 || data.tags.length > 12) {",
  "  throw new Error(",
  "    'Tags must contain 8 to 12 items. Got: ' +",
  "    data.tags.length",
  "  );",
  "}",
  "",
  "for (const tag of data.tags) {",
  "  if (!/^[a-z0-9_-]+$/.test(tag)) {",
  "    throw new Error(",
  "      'Invalid tag. Tags must be lowercase English keywords: ' +",
  "      tag",
  "    );",
  "  }",
  "}",
  "",
  "// ----------------------------------------------------------",
  "// Always use Kokoro Bella",
  "// ----------------------------------------------------------",
  "",
  "data.voice = 'af_bella';",
  "data.speed = 1.0;",
  "",
  "// ----------------------------------------------------------",
  "// Output metadata for the video renderer",
  "// ----------------------------------------------------------",
  "",
  "data.video = {",
  "  width: 1080,",
  "  height: 1920,",
  "  aspect_ratio: '9:16',",
  "  max_duration_seconds: 180,",
  "  subtitle_language: 'ar',",
  "  voice_language: 'en-us',",
  "  voice: 'af_bella',",
  "  graphic_style: 'modern-shorts-v1'",
  "};",
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
  "if (!Array.isArray(item.scenes) || item.scenes.length < 5) {",
  "  throw new Error('Build Job: expected at least 5 validated scenes.');",
  "}",
  "",
  "const job = {",
  "  voice: 'af_bella',",
  "  speed: 1.0,",
  "  language: 'en-us',",
  "  subtitle_language: 'ar',",
  "  video: {",
  "    width: 1080,",
  "    height: 1920,",
  "    aspect_ratio: '9:16',",
  "    max_duration_seconds: 180",
  "  },",
  "  graphics: {",
  "    style: 'modern-shorts-v1',",
  "    hook: String(item.hook || item.scenes[0].text_en).trim(),",
  "    progress_bar: true,",
  "    dark_overlay: true,",
  "    animated_subtitles: true,",
  "    keyword_popups: true,",
  "    scene_transitions: true",
  "  },",
  "  scenes: item.scenes.map(scene => ({",
  "    text_en: String(scene.text_en || '').trim(),",
  "    text_ar: String(scene.text_ar || '').trim(),",
  "    pexels_query: String(scene.pexels_query || 'nature').trim()",
  "  }))",
  "};",
  "",
  "const english = job.scenes",
  "  .map(scene => scene.text_en)",
  "  .join(' ');",
  "",
  "if (/[\\u0600-\\u06FF]/.test(english)) {",
  "  throw new Error(",
  "    'Build Job blocked Arabic text from reaching Kokoro.'",
  "  );",
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
  "    hook: item.hook,",
  "    voice: 'af_bella',",
  "    speed: 1.0",
  "  }",
  "}];"
].join("\n");

// ============================================================
// PRODUCE COMMAND
// ============================================================

const produceCommand =
  "mkdir -p {{ $json.runDir }} && " +
  "printf '%s' '{{ $json.jobB64 }}' | base64 -d > {{ $json.runDir }}/job.json && " +
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
    // PARSE + VALIDATE
    // --------------------------------------------------------

    {
      parameters: {
        jsCode: parseScriptCode
      },

      id: "node-parse",

      name: "Parse + Validate Script",

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
          "={{ $('Parse + Validate Script').item.json.title }}",

        categoryId: "27",

        binaryProperty: "data",

        options: {

          description:
            "={{ $('Parse + Validate Script').item.json.description }}",

          privacyStatus: "private",

          tags:
            "={{ ($('Parse + Validate Script').item.json.tags || []).join(',') }}"

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
            node: "Parse + Validate Script",
            type: "main",
            index: 0
          }
        ]
      ]
    },

    "Parse + Validate Script": {
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
           
