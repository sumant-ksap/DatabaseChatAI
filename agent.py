import os

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from database import get_schema_text, describe_table_text, execute_query, find_documents, format_query_results


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_db_schema() -> str:
    """
    Returns the schema of the connected database, listing PostgreSQL tables or
    MongoDB collections with inferred fields. Call this first whenever you need
    to understand what data exists before querying.
    """
    return get_schema_text()


@tool
def describe_table(table_name: str) -> str:
    """
    Returns the columns and data types of one table, view or collection. Use the
    exact name listed by get_db_schema, including the schema prefix if shown
    (e.g. "sales.orders"). Call this when get_db_schema omits columns.
    """
    return describe_table_text(table_name)


@tool
def execute_sql_query(sql: str) -> str:
    """
    Execute a SQL query against the connected PostgreSQL database and return the
    results as a formatted table. Use standard PostgreSQL syntax. Prefer SELECT
    for read-only queries. Wrap table or column names that contain spaces or
    uppercase letters in double quotes. Never guess data — always query it.

    Example queries:
      SELECT * FROM "orders" LIMIT 10;
      SELECT COUNT(*) FROM "customers";
      SELECT * FROM sales.invoices LIMIT 10;   -- table in a non-public schema
      SELECT status, COUNT(*) FROM "shipments" GROUP BY status;
    """
    try:
        rows = execute_query(sql)
        return format_query_results(rows)
    except Exception as exc:
        return f"SQL Error: {exc}"


@tool
def find_mongo_documents(collection_name: str, filter_json: str = "{}", limit: int = 20) -> str:
    """
    Query the connected MongoDB database and return matching documents.
    filter_json must be a valid MongoDB find filter encoded as JSON.

    Example:
      collection_name: customers
      filter_json: {"status": "active"}
      limit: 10
    """
    try:
        rows = find_documents(collection_name, filter_json=filter_json, limit=limit)
        return format_query_results(rows)
    except Exception as exc:
        return f"MongoDB Error: {exc}"


tools = [get_db_schema, describe_table, execute_sql_query, find_mongo_documents]

# ── Model ─────────────────────────────────────────────────────────────────────

_ollama_model = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")
_ollama_api_key = os.environ.get("OLLAMA_API_KEY", "")

if _ollama_api_key:
    # The local ollama daemon only proxies :cloud models on behalf of an
    # `ollama signin`-authenticated machine — OLLAMA_API_KEY doesn't apply to
    # that path. Call Ollama Cloud's API directly instead, which does accept it.
    llm = ChatOllama(
        model=_ollama_model.removesuffix("-cloud"),
        temperature=0,
        base_url="https://ollama.com",
        client_kwargs={"headers": {"Authorization": f"Bearer {_ollama_api_key}"}},
    )
else:
    llm = ChatOllama(
        model=_ollama_model,
        temperature=0,
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = SystemMessage(content=(
    "You are a data assistant connected to a live PostgreSQL or MongoDB database. "
    "You can explore the connected database and answer questions about its data.\n\n"
    "Workflow:\n"
    "1. When asked about data, first call get_db_schema to understand what tables or collections exist. "
    "If it omits columns, call describe_table for the tables you need.\n"
    "2. For PostgreSQL, write PostgreSQL SQL and call execute_sql_query to fetch real data. "
    "Tables may live in several schemas: always use schema-qualified names (schema.table) exactly as "
    "get_db_schema lists them.\n"
    "3. For MongoDB, call find_mongo_documents with a collection name and JSON filter.\n"
    "4. Summarise the results clearly in plain language.\n\n"
    "Never fabricate data. Always derive your answers from actual query results. "
    "If the user asks to modify data, confirm the operation before executing it."
))

# ── Graph ─────────────────────────────────────────────────────────────────────

def assistant(state: MessagesState):
    messages = [SYSTEM_PROMPT] + state["messages"]
    return {"messages": [llm_with_tools.invoke(messages)]}


builder = StateGraph(MessagesState)
builder.add_node("assistant", assistant)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "assistant")
builder.add_conditional_edges("assistant", tools_condition)
builder.add_edge("tools", "assistant")

agent = builder.compile()


# ── Public API ────────────────────────────────────────────────────────────────

def run_agent(user_message: str, history: list[dict] | None = None) -> str:
    """
    Send a message to the agent and return the final text response.

    history: list of {"role": "user"|"assistant", "content": "..."} dicts
             representing prior turns. Pass None or [] for a fresh conversation.
    """
    messages = []
    for turn in (history or []):
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=user_message))

    result = agent.invoke({"messages": messages})
    return result["messages"][-1].content
