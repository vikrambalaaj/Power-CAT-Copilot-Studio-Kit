# MCP Apps

Ready-to-deploy MCP Copilot apps, packaged as self-contained zips.

> **What is an MCP App?** An MCP App is an extension to the Model Context Protocol (MCP) that lets an MCP server deliver rich, interactive UI widgets to its host. In these samples, that host is Microsoft 365 Copilot — so tool responses render as interactive cards, lists, and forms instead of plain text.

## Available apps

| Folder | Package | App |
|---|---|---|
| `ask-salesforce` | `ask-salesforce.zip` | Ask - Salesforce CRM Copilot |
| `ask-servicenow` | `ask-servicenow.zip` | Ask - ServiceNow ITSM Copilot |
| `ask-successfactors` | Build from source | Velora Executive Agent: SuccessFactors + S/4HANA design |
| `ask-s4hana` | Build from source | SAP S/4HANA finance MCP used by the Velora Executive Agent |

## Getting started

1. Open the folder for the app you want (see the table above).
2. Follow the `README.md` inside that folder.

Each in-folder README describes its deployment and configuration model.

For the Velora Executive Agent, start with the source and architecture documents. Do not deploy an old local ZIP: packages must be rebuilt after both MCP URLs and authentication references are configured.
