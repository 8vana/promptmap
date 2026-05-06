#!/usr/bin/env bash
# PromptMap – Environment Variable Setup
#
# Usage:
#   1. Copy this file:  cp setup_env.sh setup_env.local.sh
#   2. Fill in your keys in setup_env.local.sh
#   3. Source it:       source setup_env.local.sh
#
# setup_env.local.sh is git-ignored to prevent accidental key leaks.
# Only the provider(s) you intend to use need to be configured.

# ---------------------------------------------------------------------------
# OpenAI  (https://platform.openai.com/api-keys)
# ---------------------------------------------------------------------------
export OPENAI_API_KEY="your-openai-api-key"

# ---------------------------------------------------------------------------
# Anthropic  (https://console.anthropic.com/settings/keys)
# ---------------------------------------------------------------------------
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# ---------------------------------------------------------------------------
# Google Gemini  (https://aistudio.google.com/app/apikey)
# Either GEMINI_API_KEY or GOOGLE_API_KEY is sufficient.
# ---------------------------------------------------------------------------
export GEMINI_API_KEY="your-gemini-api-key"
# export GOOGLE_API_KEY="your-google-api-key"   # alternative

# ---------------------------------------------------------------------------
# Amazon Bedrock  (standard AWS credential chain)
# https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html
# ---------------------------------------------------------------------------
export AWS_ACCESS_KEY_ID="your-aws-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-aws-secret-access-key"
export AWS_REGION="us-west-1"
# export AWS_SESSION_TOKEN="your-session-token"  # only for temporary credentials (IAM Role / SSO)

# ---------------------------------------------------------------------------
# Ollama  (local – no API key required)
# Override only if the server runs on a non-default address.
# Default: http://localhost:11434/v1
# ---------------------------------------------------------------------------
# export OLLAMA_BASE_URL="http://localhost:11434/v1"

# ---------------------------------------------------------------------------
# Adversarial LLM / Score LLM  (optional — overrides the TUI Settings)
#
# When set, these variables override the corresponding values stored in
# ~/.promptmap_config.json on every launch. Useful for scripted / CI runs
# where you don't want to rely on the TUI-saved config.
#
# Provider must be one of: openai | anthropic | gemini | bedrock | ollama
# (the same provider needs its own credentials configured above).
# ---------------------------------------------------------------------------
# export PROMPTMAP_ADV_LLM_PROVIDER="openai"
# export PROMPTMAP_ADV_LLM_NAME="gpt-4o-mini"
# export PROMPTMAP_SCORE_LLM_PROVIDER="anthropic"
# export PROMPTMAP_SCORE_LLM_NAME="claude-3-5-sonnet-20241022"
