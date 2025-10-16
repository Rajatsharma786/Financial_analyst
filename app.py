import sys
if hasattr(sys.modules, 'items'):
    sys._safe_modules = list(sys.modules.items())
import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import pandas as pd
import re 
import os
from IPython.display import display, Markdown
from openbb import obb
import auth
from auth import SessionManager, require_auth
load_dotenv()

# Initialize OpenBB with error handling and caching
@st.cache_resource
def init_openbb():
    """Initialize OpenBB account login (cached to avoid rate limits)"""
    try:
        OPENBB_PAT = os.getenv("OPENBB_PAT")
        if OPENBB_PAT:
            obb.account.login(pat=OPENBB_PAT)
            return True
    except Exception as e:
        st.warning(f"OpenBB initialization warning: {str(e)}. Some features may be limited.")
        return False
    return False

# Initialize OpenBB once
init_openbb()

@tool
def get_stock_ticker_symbol(stock_name: str) -> str:
  """Get the symbol, name and CIK for any publicly traded company"""
  res = obb.equity.search(stock_name,provider="sec")
  stock_ticker_details = res.to_df().to_markdown()
  output = """Here are the details of the company and its stock ticker symbol:\n\n""" + stock_ticker_details
  return output

@tool
def get_stock_price_metric(stock_ticker: str) -> str:
  """Get historical stock price data, stock price quote and price performance data
       like price changes for a specific stock ticker"""
  res = obb.equity.price.quote(stock_ticker, provider='cboe')
  price_quote = res.to_df().to_markdown()
  
  res = obb.equity.price.performance(symbol=stock_ticker, provider='finviz')
  price_performance = res.to_df().to_markdown()

  end_date = datetime.now()
  start_date = (end_date - timedelta(days=182)).strftime("%Y-%m-%d")
  res = obb.equity.price.historical(symbol=stock_ticker, start_date=start_date,
                                    interval='1d', provider='yfinance')
  price_historical = res.to_df().to_markdown()
  output = ("""Here are the stock price metrics and data for the stock ticker symbol """ + stock_ticker + """: \n\n""" +
              "Price Quote Metrics:\n\n" + price_quote +
              "\n\nPrice Performance Metrics:\n\n" + price_performance +
              "\n\nPrice Historical Data:\n\n" + price_historical)
  return output

@tool
def get_stock_fundamental_indicator_metrics(stock_ticker: str) -> str:
    """Get fundamental indicator metrics for a specific stock ticker"""
    res = obb.equity.fundamental.ratios(symbol=stock_ticker, period='annual',
                                        limit=10, provider='yfinance')
    fundamental_ratios = res.to_df().to_markdown()

    res = obb.equity.fundamental.metrics(symbol=stock_ticker, period='annual',
                                        limit=10, provider='yfinance')
    fundamental_metrics = res.to_df().to_markdown()

    res = obb.equity.fundamental.income_growth(symbol=stock_ticker, period='annual',
                                        limit=10, provider='yfinance')
    income_growth = res.to_df().to_markdown()

    output = ("""Here are the fundamental indicator metrics and data for the stock ticker symbol """ + stock_ticker + """: \n\n""" +
              "Fundamental Ratios:\n\n" + fundamental_ratios +
              "\n\nFundamental Metrics:\n\n" + fundamental_metrics+
              "\n\nFundamental Income Growth:\n\n"+income_growth)
    return output
  
def _clean_summary(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    # collapse whitespace and trim
    t = re.sub(r"\s+", " ", text).strip()
    return (t[: max_len - 1] + "…") if len(t) > max_len else t
@tool
def get_stock_news(stock_ticker: str) -> str:
    """Get news article headlines for a specific stock ticker via Marketaux (with summary)."""
    try:
        api_key = os.getenv("MARKETAUX_API_KEY")
        if not api_key:
            return "Missing MARKETAUX_API_KEY. Set it as an environment variable."

        base_url = "https://api.marketaux.com/v1/news/all"
        params = {
            "symbols": stock_ticker.upper(),
            "filter_entities": "true",
            "language": "en",
            "api_token": api_key,
            "limit": 50,
            "page": 1,
        }

        articles = []
        while len(articles) < 50:
            r = requests.get(base_url, params=params, timeout=20)
            r.raise_for_status()
            payload = r.json()

            data = payload.get("data", []) or []
            if not data:
                break

            articles.extend(data)
            meta = payload.get("meta", {}) or {}
            if not meta.get("has_next_page"):
                break
            params["page"] += 1

        if not articles:
            return f"Sorry, I couldn’t find recent news for {stock_ticker.upper()}."

        rows = []
        for a in articles[:50]:
            # symbols live under `entities`
            ents = a.get("entities") or []
            syms = ",".join(e.get("symbol", "") for e in ents if e.get("symbol")) or stock_ticker.upper()

            summary = a.get("snippet") or a.get("description") or a.get("content") or ""
            summary = _clean_summary(summary, max_len=600)

            rows.append({
                "symbols": syms,
                "title": (a.get("title") or "").strip(),
                "summary": summary,
                "source": a.get("source") or "",
                "published_at": a.get("published_at") or "",
                "url": a.get("url") or "",
            })

        # Sort newest first if we have timestamps
        df = pd.DataFrame(rows)
        if "published_at" in df.columns and not df["published_at"].isna().all():
            df = df.sort_values("published_at", ascending=False)

        # Show more than just title
        news = df[["symbols", "title", "summary","url"]].to_markdown(index=False)

        return (
            f"Here are the recent news headlines for the stock ticker symbol {stock_ticker.upper()}:\n\n{news}\n\n"
            "Tip: each row also has `url` if you want to open the article."
        )

    except Exception as e:
        return f"Sorry, I could not retrieve news for the stock ticker symbol {stock_ticker.upper()}: {e}"

@tool 
def get_general_market_data() -> str:
    """Get general data and indicators for the whole stock market including,
       most actively traded stocks based on volume, top price gainers and top price losers.
       Useful when you want an overview of the market and what stocks to look at."""

    res = obb.equity.discovery.active(sort='desc', provider='yfinance', limit=15)
    most_active_stocks = res.to_df().to_markdown()

    res = obb.equity.discovery.gainers(sort='desc', provider='yfinance', limit=15)
    price_gainers = res.to_df().to_markdown()


    res = obb.equity.discovery.losers(sort='desc', provider='yfinance', limit=15)
    price_losers = res.to_df().to_markdown()
    

    res = obb.equity.discovery.undervalued_growth(sort='desc', provider='yfinance', limit=15)
    undervalued_growth = res.to_df().to_markdown()

    output = ("""Here's some detailed information of the stock market which includes most actively traded stocks, gainers and losers:\n\n""" +
              "Most actively traded stocks:\n\n" + most_active_stocks +
              "\n\nTop price gainers:\n\n" + price_gainers +
              "\n\nTop price losers:\n\n" + price_losers+
              "\n\nUnderValue Growth:\n\n"+undervalued_growth)
    return output

tools = [get_stock_ticker_symbol,
         get_stock_price_metric,
         get_stock_fundamental_indicator_metrics,
         get_stock_news,
         get_general_market_data]
         
# Email configuration is handled by the scheduler service
# No need to check email config in the Streamlit app

AGENT_PREFIX = """Role: You are an AI stock market assistant tasked with providing investors
with up-to-date, detailed information on individual stocks or advice based on general market data.

Objective: Assist data-driven stock market investors by giving accurate,
complete, but concise information relevant to their questions about individual
stocks or general advice on useful stocks based on general market data and trends.

Capabilities: You are given a number of tools as functions. Use as many tools
as needed to ensure all information provided is timely, accurate, concise,
relevant, and responsive to the user's query.

Starting Flow:
Input validation. Determine if the input is asking about a specific company
or stock ticker (Flow 2). If not, check if they are asking for general advice on potentially useful stocks
based on current market data (Flow 1). Otherwise, respond in a friendly, positive, professional tone
that you don't have information to answer as you can only provide financial advice based on market data.
For each of the flows related to valid questions use the following instructions:

Flow 1:
A. Market Analysis: If the query is valid and the user wants to get general advice on the market
or stocks worth looking into for investing, leverage the general market data tool to get relevant data.

Flow 2:
A. Symbol extraction. If the query is valid and is related to a specific company or companies,
extract the company name or ticker symbol from the question.
If a company name is given, look up the ticker symbol using a tool.
If the ticker symbol is not found based on the company, try to
correct the spelling and try again, like changing "microsfot" to "microsoft",
or broadening the search, like changing "southwest airlines" to a shorter variation
like "southwest" and increasing "limit" to 10 or more. If the company or ticker is
still unclear based on the question or conversation so far, and the results of the
symbol lookup, then ask the user to clarify which company or ticker.

B. Information retrieval. Determine what data the user is seeking on the symbol
identified. Use the appropriate tools to fetch the requested information. Only use
data obtained from the tools. You may use multiple tools in a sequence. For instance,
first determine the company's symbol, then retrieve price data using the symbol
and fundamental indicator data etc. For specific queries only retrieve data using the most relevant tool.
If detailed analysis is needed, you can call multiple tools to retrieve data first.

Response Generation Flow:
Compose Response. Analyze the retrieved data carefully and provide a comprehensive answer to the user in a clear and concise format,
in a friendly professional tone, emphasizing the data retrieved.
If the user asks for recommendations you can give some recommendations
but emphasize the user to do their own research before investing.
When generating the final response in markdown,
if there are special characters in the text, such as the dollar symbol,
ensure they are escaped properly for correct rendering e.g $25.5 should become \$25.5

Example Interaction:
User asks: "What is the PE ratio for Eli Lilly?"
Chatbot recognizes 'Eli Lilly' as a company name.
Chatbot uses symbol lookup to find the ticker for Eli Lilly, returning LLY.
Chatbot retrieves the PE ratio using the proper function with symbol LLY.
Chatbot responds: "The PE ratio for Eli Lilly (symbol: LLY) as of May 12, 2024 is 30."

User asks: "Here are the top 5 trending news headlines based on the most active stocks in the market:
chatbot lookup trending news.
chatbot retrieves the most trending news using the proper function.
chatbot responds with the top 5 trending news headlines:
    1. **Apple Inc. (AAPL)**: 'Apple unveils new iPhone models with groundbreaking features.'
    2. **Tesla Inc. (TSLA)**: 'Tesla announces record-breaking quarterly earnings.'
    3. **Microsoft Corp. (MSFT)**: 'Microsoft expands AI capabilities in its cloud services.'
    4. **Amazon.com Inc. (AMZN)**: 'Amazon launches new drone delivery service.'
    5. **NVIDIA Corp. (NVDA)**: 'NVIDIA reveals next-generation GPUs for AI applications.'

Check carefully and only call the tools which are specifically named below.
Only use data obtained from these tools.
"""

SYS_PROMPT = SystemMessage(content=AGENT_PREFIX)

chatgpt = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)

# Initialize and persist MemorySaver and agent across reruns
if 'memory' not in st.session_state:
    st.session_state.memory = MemorySaver()

if 'financial_analyst' not in st.session_state:
    st.session_state.financial_analyst = create_react_agent(
        model=chatgpt,
        tools=tools,
        prompt=SYS_PROMPT,
        checkpointer=st.session_state.memory
    )

# Check if user is authenticated
if auth.render_auth_page():
    # User is authenticated, show the main application
    # Import the user profile page
    import user_profile
    
    # Get current user
    user = SessionManager.get_current_user()
    
    # Initialize session state for chat history and thread after authentication
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    # Set thread_id based on authenticated user
    if 'thread_id' not in st.session_state or st.session_state.get('current_user') != user.get('username'):
        if user:
            st.session_state.thread_id = user['username']
            st.session_state.current_user = user['username']
        else:
            st.session_state.thread_id = "default_thread"

    # Navigation menu
    menu = ["Home", "My Profile"]
    choice = st.sidebar.selectbox("Navigation", menu)
    
    if choice == "Home":
        st.title("Financial Analyst Assistant")
        
        # Display user welcome message
        if user:
            st.write(f"Welcome, {user['username']}!")
        
        # Display chat history
        st.subheader("Chat History")
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(message["content"])
                elif message["role"] == "assistant":
                    with st.chat_message("assistant"):
                        st.markdown(message["content"])
        
        # Main app functionality
        query = st.chat_input("Ask your financial question (e.g., Compare Nvidia and Intel)")
        
        if query:
            # Add user message to chat history
            st.session_state.chat_history.append({"role": "user", "content": query})
            
            # Display user message
            with st.chat_message("user"):
                st.markdown(query)
            
            # Display assistant response with streaming
            with st.chat_message("assistant"):
                response_placeholder = st.empty()

                # Stream the agent's response
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                
                try:
                    agent = st.session_state.financial_analyst
                    accumulated = ""

                    # Primary: token/partial streaming via updates
                    for update in agent.stream(
                        {"messages": [HumanMessage(content=query)]},
                        config=config,
                        stream_mode="updates",
                    ):
                        try:
                            # update is a dict of event_name -> payload
                            for _, payload in (update.items() if isinstance(update, dict) else []):
                                if isinstance(payload, dict):
                                    # Token chunks (common key: "chunk")
                                    if "chunk" in payload:
                                        chunk = payload["chunk"]
                                        text_part = ""
                                        # AIMessageChunk has .content that might be str or list of parts
                                        content = getattr(chunk, "content", None)
                                        if isinstance(content, str):
                                            text_part = content
                                        elif isinstance(content, list):
                                            for part in content:
                                                if isinstance(part, dict) and part.get("type") == "text":
                                                    text_part += part.get("text", "")
                                        if text_part:
                                            accumulated += text_part
                                            response_placeholder.markdown(accumulated + "▌")
                                    # Sometimes we receive full messages via values inside an update
                                    elif "messages" in payload and isinstance(payload["messages"], list):
                                        msgs = payload["messages"]
                                        if msgs and isinstance(msgs[-1], AIMessage) and isinstance(msgs[-1].content, str):
                                            accumulated = msgs[-1].content
                                            response_placeholder.markdown(accumulated + "▌")
                        except Exception:
                            # Ignore parsing issues for unknown update shapes
                            pass

                    full_response = accumulated

                    # Fallback: if nothing accumulated, try values mode once to get final message
                    if not full_response:
                        for event in agent.stream(
                            {"messages": [HumanMessage(content=query)]},
                            config=config,
                            stream_mode="values",
                        ):
                            if isinstance(event, dict) and "messages" in event and event["messages"]:
                                last_message = event["messages"][-1]
                                if isinstance(last_message, AIMessage) and isinstance(last_message.content, str):
                                    full_response = last_message.content
                                    response_placeholder.markdown(full_response)

                    # Display final response without cursor and save
                    if full_response:
                        response_placeholder.markdown(full_response)
                        st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                    else:
                        fallback_msg = "I couldn't generate a response. Please try again."
                        response_placeholder.markdown(fallback_msg)
                        st.session_state.chat_history.append({"role": "assistant", "content": fallback_msg})
                        
                except Exception as e:
                    error_msg = f"An error occurred: {str(e)}"
                    response_placeholder.markdown(error_msg)
                    st.session_state.chat_history.append({"role": "assistant", "content": error_msg})
                    st.error(f"Error details: {e}")
        
        # Clear chat history button
        if st.button("Clear Chat History"):
            st.session_state.chat_history = []
            st.rerun()
        
        # Newsletter promo
        st.sidebar.markdown("---")
        st.sidebar.subheader("📰 Stock Newsletter")
        if user and user.get('signed_up_for_newsletter', False):
            st.sidebar.success("You're subscribed to our daily stock newsletter!")
        else:
            st.sidebar.info("Subscribe to our daily stock newsletter to get updates on your favorite stocks.")
            if st.sidebar.button("Subscribe Now"):
                st.sidebar.markdown("Go to 'My Profile' to manage your subscription.")
    
    elif choice == "My Profile":
        # Render the profile page
        user_profile.render_profile_page()
    
    # Logout button in the sidebar
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        SessionManager.logout_user()
        st.rerun()
# If not authenticated, the auth page is already displayed by render_auth_page()