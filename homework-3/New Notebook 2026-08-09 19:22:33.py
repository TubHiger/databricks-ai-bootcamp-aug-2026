# Databricks notebook source
# MAGIC %pip install -q databricks-mcp databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks_mcp import DatabricksMCPClient

APP_MCP_URL = "https://weather-forecast-mcp-7474645680347061.aws.databricksapps.com/mcp"

w = WorkspaceClient()
client = DatabricksMCPClient(server_url=APP_MCP_URL, workspace_client=w)

tools = client.list_tools()
print("TOOLS:", [t.name for t in tools])

result = client.call_tool("get_current_weather", {"location": "Chicago"})
print(result.content[0].text)