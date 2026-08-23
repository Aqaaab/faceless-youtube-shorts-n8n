#!/usr/bin/env node
'use strict';

/**
 * Validates and normalizes the importable n8n workflow.
 *
 * The workflow is maintained as JSON in:
 *   workflows/youtube-shorts-automation.json
 *
 * This script intentionally does not construct a second copy of the workflow
 * in JavaScript. Keeping one source of truth prevents the generated workflow
 * and the checked-in workflow from drifting apart.
 *
 * Usage:
 *   node build_workflow.js
 */

const fs = require('fs');
const path = require('path');

const root = __dirname;
const workflowPath = path.join(
  root,
  'workflows',
  'youtube-shorts-automation.json'
);

function fail(message) {
  console.error(`WORKFLOW_VALIDATION_ERROR: ${message}`);
  process.exit(1);
}

if (!fs.existsSync(workflowPath)) {
  fail(`workflow file not found: ${workflowPath}`);
}

let workflow;
try {
  workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
} catch (error) {
  fail(`invalid workflow JSON: ${error.message}`);
}

if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) {
  fail('workflow root must be a JSON object');
}

if (!Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
  fail('workflow must contain at least one node');
}

if (!workflow.connections || typeof workflow.connections !== 'object') {
  fail('workflow is missing connections');
}

const nodeNames = new Set();
for (const node of workflow.nodes) {
  if (!node || typeof node !== 'object') {
    fail('workflow contains an invalid node');
  }

  if (!node.name || !node.type) {
    fail('every node must have name and type');
  }

  if (nodeNames.has(node.name)) {
    fail(`duplicate node name: ${node.name}`);
  }

  nodeNames.add(node.name);
}

for (const [source, branches] of Object.entries(workflow.connections)) {
  if (!nodeNames.has(source)) {
    fail(`connection source does not exist: ${source}`);
  }

  if (!branches || typeof branches !== 'object' || !Array.isArray(branches.main)) {
    fail(`invalid connection definition for: ${source}`);
  }

  for (const branch of branches.main) {
    if (!Array.isArray(branch)) continue;
    for (const connection of branch) {
      if (!connection || !nodeNames.has(connection.node)) {
        fail(
          `connection from ${source} points to a missing node: ${
            connection && connection.node
          }`
        );
      }
    }
  }
}

// Normalize the JSON formatting without changing workflow semantics.
fs.writeFileSync(
  workflowPath,
  `${JSON.stringify(workflow, null, 2)}\n`,
  'utf8'
);

console.log(`WORKFLOW_VALIDATION: PASS (${workflow.nodes.length} nodes)`);
console.log(`WORKFLOW_FILE: ${path.relative(root, workflowPath)}`);
