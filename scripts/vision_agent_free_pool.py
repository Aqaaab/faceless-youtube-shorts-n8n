#!/usr/bin/env python3
"""Compatibility vision pool: BlockRun free Omni first, Hugging Face VL second."""
from __future__ import annotations
import base64,json,os,urllib.request,urllib.error
from pathlib import Path

def payload(prompt,images):
    return [{"type":"text","text":prompt}]+[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+base64.b64encode(Path(p).read_bytes()).decode()}} for p in images]

def call_blockrun(prompt,images):
    body={"model":os.getenv("BLOCKRUN_VISION_MODEL","nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"),"messages":[{"role":"system","content":"Return ONLY one valid JSON object. You are a strict visual QA engine."},{"role":"user","content":payload(prompt,images)}],"temperature":0,"max_tokens":3000}
    req=urllib.request.Request("https://blockrun.ai/api/v1/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer not-needed-for-free-models","Content-Type":"application/json","Accept":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=120) as r:return r.read().decode()

def call_hf(prompt,images,key):
    body={"model":os.getenv("HF_VISION_MODEL","nvidia/nemotron-nano-12b-v2-vl"),"messages":[{"role":"system","content":"Return ONLY one valid JSON object. You are a strict visual QA engine."},{"role":"user","content":payload(prompt,images)}],"temperature":0,"max_tokens":3000}
    req=urllib.request.Request("https://router.huggingface.co/v1/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","Accept":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=120) as r:return r.read().decode()
