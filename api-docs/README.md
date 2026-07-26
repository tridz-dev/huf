# HUF APIs - Bruno Collection

This directory contains the Bruno API collection for **HUF APIs**. It provides a set of pre-configured HTTP requests to interact with the HUF AI and Agent infrastructure.

## Getting Started

1. **Install Bruno**: If you haven't already, install the [Bruno API client](https://www.usebruno.com/).
2. **Open Collection**: Open Bruno and choose to open an existing collection. Select the `api-docs/bruno/huf_apis` directory.
3. **Configure Environment variables**: The collection uses the following environment variables which you may need to set or override in your Bruno environment:
   - `BASE_URL`: The base URL of your HUF ERPNext/Frappe instance (e.g., `https://api.yourdomain.com`).
   - `Agent_Name`: The name of the AI agent you want to interact with (e.g., `Demo Agent`).
   - `Prompt`: The prompt or message you want to send to the agent.

## Available Endpoints

The collection includes endpoints for managing and interacting with various parts of the system:

- **Authentication**:
  - `Login`: Authenticate with the API.

- **AI Agents**:
  - `Run Agent Sync`: Run an agent synchronously and get the response.
  - `Agent Stream`: Stream responses from an agent.
  - `Agent Creation`: Create a new AI agent.
  
- **Agent Data & History**:
  - `Agent Conversation`: Fetch conversation history for agents.
  - `Agent Message`: Access individual agent messages.
  - `Agent Run`: View data for specific agent executions.

- **Providers & Models**:
  - `AI Providers`: Manage AI service providers (e.g., OpenAI, Anthropic).
  - `AI Provider Creation`: Create a new AI provider.
  - `AI Models`: View available AI models.
  - `AI Model Creation`: Add a new AI model to the system.

## Authentication
Most requests require authentication. Make sure you run the `Login` request first or ensure that your proxy/auth settings are properly configured in Bruno so that session cookies or tokens are inherited.
