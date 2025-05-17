import json
import threading
import asyncio
import websocket
from nicegui import ui, app
from queue import Queue
import time
import sqlalchemy
import logging
import datetime
import decimal

# Global variables to track connection state
ws_connection = None
connected_username = None
message_queue = Queue()  # Queue for thread-safe message passing

def execute_test_connection(connectionObject, query="SELECT 1"):
    """Executes a test query using SQLAlchemy and returns (success, message, tables)."""
    try:
        # Build SQLAlchemy URL
        dialect = connectionObject.get("dialect", "mysql")
        user = connectionObject["user"]
        password = connectionObject["password"]
        host = connectionObject["host"]
        port = connectionObject["port"]
        database = connectionObject["database"]
        schema = connectionObject.get("schema", None)
        if dialect == "postgresql":
            url = f"postgresql://{user}:{password}@{host}:{port}/{database}/{schema}"
        elif dialect == "mysql":
            url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        else:
            url = f"{dialect}://{user}:{password}@{host}:{port}/{database}"
        print(f"URL: {url}")
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            # Run the test query
            conn.execute(sqlalchemy.text(query))
            # Get table list
            inspector = sqlalchemy.inspect(engine)
            tables = inspector.get_table_names(schema=database)
        return True, "Tunnel mode: Connection successful", tables
    except Exception as e:
        print(f"Error: {e}")
        return False, f"Tunnel mode: {str(e)}", []

def ws_thread(url, username, password):
    global ws_connection, connected_username
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("dave_router.ws_thread")
    try:
        ws = websocket.create_connection(url)
        ws_connection = ws
        
        # Send login
        ws.send(json.dumps({"username": username, "password": password}))
        resp = ws.recv()
        resp_data = json.loads(resp)
        
        if not resp_data.get("success"):
            message_queue.put({"type": "login_failed", "message": f"Login failed: {resp_data.get('message', '')}"})
            ws.close()
            ws_connection = None
            return
            
        connected_username = username
        message_queue.put({"type": "connected", "message": f"Connected as {username}"})
        
        # Keep alive
        while True:
            msg = ws.recv()
            logger.debug(f"Received raw message: {msg}")
            print(f"Received message: {msg}")
            # Try to parse as JSON for tunnel mode
            try:
                data = json.loads(msg)
                if data.get("type") == "sql-query":
                    logger.info(f"Received sql-query: request_id={data.get('request_id')}, query={data.get('query')}, connectionObject={data.get('connectionObject')}")
                    # message_queue.put({"type": "info", "message": f"Executing query: {data.get('query', '')}"})
                    connectionObject = data["connectionObject"]
                    query = data.get("query", "SELECT 1")
                    queryParams = data.get("queryParams", None)
                    request_id = data.get("request_id")

                    # Prepare detailed event for sql execution info
                    sql_query_event = {
                        "type": "sql_execution_info",
                        "query": query,
                        "connectionObject": connectionObject,
                        "queryParams": queryParams,
                        "request_id": request_id,
                        "message": f"Executing query (ID: {request_id}): {query[:100]}{'...' if len(query) > 100 else ''}" # Original message for fallback/logging
                    }
                    message_queue.put(sql_query_event)

                    response = {
                        "type": "sql-query-result",
                        "request_id": request_id,
                        "success": False,
                        "message": "",
                        "keys": [],
                        "rows": [],
                        "rowcount": -1
                    }
                    try:
                        # Build SQLAlchemy URL
                        dialect = connectionObject.get("dialect", "mysql")
                        user = connectionObject["user"]
                        password = connectionObject["password"]
                        host = connectionObject["host"]
                        port = connectionObject["port"]
                        database = connectionObject["database"]
                        schema = connectionObject.get("schema", None)
                        if dialect == "postgresql":
                            url = f"postgresql://{user}:{password}@{host}:{port}/{database}/{schema}" if schema else f"postgresql://{user}:{password}@{host}:{port}/{database}"
                        elif dialect == "mysql":
                            url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
                        else:
                            url = f"{dialect}://{user}:{password}@{host}:{port}/{database}"
                        logger.info(f"Connecting to DB: {url}")
                        engine = sqlalchemy.create_engine(url)
                        with engine.connect() as conn:
                            # Use SQLAlchemy text for parametrized queries
                            stmt = sqlalchemy.text(query)
                            logger.info(f"Executing SQL: {query} with params: {queryParams}")
                            result = conn.execute(stmt, queryParams or {})
                            # Try to fetch results if it's a SELECT
                            if result.returns_rows:
                                rows = result.fetchall()
                                keys = result.keys()
                                response["keys"] = list(keys)
                                response["rows"] = [[convert_json_safe(cell) for cell in row] for row in rows]
                                response["rowcount"] = result.rowcount if result.rowcount is not None else len(rows)
                                # Scalar result if only one row and one column
                                if len(rows) == 1 and len(rows[0]) == 1:
                                    response["scalar_result"] = convert_json_safe(rows[0][0])
                            else:
                                response["rowcount"] = result.rowcount
                            # Optionally, return tables if requested (for metadata queries)
                            if query.strip().lower() in ("show tables", "select table_name from information_schema.tables where table_schema = database()"):
                                inspector = sqlalchemy.inspect(engine)
                                response["tables"] = inspector.get_table_names(schema=database)
                            response["success"] = True
                            response["message"] = "Query executed successfully"
                            message_queue.put({"type": "sql_success", "message": f"SQL Success: {response['rowcount']} row(s) returned."})
                            logger.info(f"Query success: request_id={request_id}, rowcount={response['rowcount']}")
                    except Exception as e:
                        response["success"] = False
                        response["message"] = str(e)
                        message_queue.put({"type": "sql_error", "message": f"SQL Error: {str(e)}"})
                        logger.error(f"Query error: request_id={request_id}, error={str(e)}")
                    logger.info(f"Sending response: request_id={request_id}, success={response['success']}, rowcount={response['rowcount']}")
                    ws.send(json.dumps(response))
                    continue
            except Exception as e:
                logger.error(f"Exception in ws_thread message handler: {str(e)}")
                pass
            # message_queue.put(f"Received: {msg}")
    except Exception as e:
        message_queue.put({"type": "disconnected", "message": "Disconnected"})
        ws_connection = None
        connected_username = None

# NiceGUI interface
def create_ui():
    # Set the background color outside the card and ensure full height
    ui.add_head_html("""
    <style>
        body {
            background-color: #020617 !important;
            margin: 0;
            padding: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        /* Make sure the NiceGUI container takes full height */
        #nicegui-content {
            display: flex;
            flex-direction: column;
            flex-grow: 1;
            height: 100%;
        }
        
        /* Terminal styling */
        .terminal {
            background-color: #1a1a1a;
            border-radius: 6px;
            color: #f0f0f0;
            font-family: monospace;
            height: 100%;
            overflow-y: auto;
            padding: 12px;
        }
        
        .terminal-message {
            border-bottom: 1px solid #333;
            padding: 6px 0;
            white-space: pre-wrap;
            word-break: break-word;
        }
        
        .terminal-message:last-child {
            border-bottom: none;
        }
        
        .terminal-time {
            color: #888;
            margin-right: 8px;
        }
        
        .terminal-success {
            color: #4caf50;
        }
        
        .terminal-error {
            color: #f44336;
        }
        
        .terminal-info {
            color: #2196f3;
        }
    </style>
    """)

    # Container for vertical centering
    with ui.column().classes('w-full h-full flex items-center justify-center'):
        # Create a row with two cards
        with ui.row().classes('w-full px-4 gap-4 flex-row justify-center items-stretch max-w-7xl'):
            # Left card - Login (30% width)
            with ui.card().classes('w-[25%] p-6 rounded-xl shadow-lg bg-[#FCFCFA] dark:bg-gray-800 h-[90vh] flex flex-col'):
                ui.label('Dave Tunnel Mode Router').classes('text-xl font-semibold text-center text-gray-700 dark:text-gray-200 mb-4')

                # Status image - initially disconnected (with flex-shrink-0 to prevent image compression)
                status_image = ui.image('dave_disconnected.png').classes('w-32 h-32 mx-auto flex-shrink-0')

                # Inputs with updated styling
                username_input = ui.input(label='Username').classes('w-full mb-2 mt-4').props('outlined dense')
                password_input = ui.input(label='Password', password=True).classes('w-full mb-4').props('outlined dense')

                # Status label centered below image
                status_label = ui.label('Not Connected').classes('w-full text-center text-sm text-gray-500 dark:text-gray-400 mb-2')

                # Spacer to push button to bottom
                ui.element('div').classes('flex-grow')

                # Create both buttons but only one will be visible at a time
                with ui.row().classes('w-full justify-center mt-auto'):
                    login_button = ui.button('Login', on_click=lambda: on_login_click()).props('color=primary rounded w-full')
                    disconnect_button = ui.button('Disconnect', on_click=lambda: disconnect_ws()).props('color=negative rounded w-full')
                    # Initially hide the disconnect button
                    disconnect_button.visible = False

            # Right card - Terminal display (70% width)
            with ui.card().classes('w-[70%] p-0 rounded-xl shadow-lg overflow-hidden h-[90vh] flex flex-col bg-gray-800'):
                # Terminal header with title and stats
                with ui.row().classes('w-full h-full text-white pb-8 p-3 items-center'):
                    ui.label('Message Queue').classes('text-lg font-medium')
                    ui.space()
                    def clear_logs():
                        message_history.clear()
                        terminal_container.clear()
                        message_count.text = 'Messages: 0'
                    ui.button(on_click=clear_logs, icon='delete').props('color=error flat dense').classes('mr-2').style('color: #ef4444').tooltip('Clear logs')
                    connection_status = ui.label('Disconnected').classes('text-sm rounded px-2 py-1 bg-red-500')
                    ui.label('|').classes('mx-2 text-gray-500')
                    message_count = ui.label('Messages: 0').classes('text-sm')
                    terminal_container = ui.scroll_area().classes('w-full h-full terminal-container flex-grow')
                    terminal_scroll_area = terminal_container  # Save reference for scrolling

        # Store message history
        message_history = []
        # Buffer for pending terminal messages
        pending_terminal_messages = []
        
        def flush_terminal_messages():
            """Flush all buffered terminal messages to the UI at once."""
            nonlocal pending_terminal_messages
            for args in pending_terminal_messages:
                _add_terminal_message_to_ui(*args)
            pending_terminal_messages.clear()
            message_count.text = f"Messages: {len(message_history)}"
            if terminal_scroll_area:
                terminal_scroll_area.scroll_to(percent=100)

        def _add_terminal_message_to_ui(content_or_data, type="normal"):
            """Internal: Actually add a message to the terminal UI and message_history."""
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            if type == "sql_query" and isinstance(content_or_data, dict):
                query_data = content_or_data
                raw_query = query_data.get('query', '')
                display_query = " ".join(raw_query.split()).strip()
                max_len = 70
                if len(display_query) > max_len:
                    summary_text = f"{display_query[:max_len-3]}..."
                else:
                    summary_text = display_query
                display_text = f"Executing Query: {summary_text}"
                message_history.insert(0, (timestamp, display_text, "info_clickable", query_data))
                with terminal_container:
                    new_row = ui.row().classes('terminal-message w-full items-center')
                    with new_row:
                        ui.label(f"[{timestamp}]").classes('terminal-time')
                        clickable_label = ui.label(display_text).classes(f'flex-grow terminal-info cursor-pointer hover:underline')
                        clickable_label.on('click', lambda _, qd=query_data: show_sql_query_dialog(qd))
            else:
                text_content = str(content_or_data.get("message") if isinstance(content_or_data, dict) and "message" in content_or_data else content_or_data)
                message_history.insert(0, (timestamp, text_content, type))
                with terminal_container:
                    new_row = ui.row().classes('terminal-message w-full')
                    with new_row:
                        ui.label(f"[{timestamp}]").classes('terminal-time')
                        msg_class = f"terminal-{type}" if type in ["success", "error", "info"] else ""
                        ui.label(text_content).classes(f'flex-grow {msg_class}')

        def add_terminal_message(content_or_data, type="normal"):
            """Buffer a message to be added to the terminal UI on the next flush."""
            pending_terminal_messages.append((content_or_data, type))

        def show_sql_query_dialog(query_data):
            with ui.dialog() as dialog, ui.card().classes(
                'min-w-[600px] max-w-[80vw] dark:bg-gray-800 rounded-lg shadow-xl' # Dark mode, rounded, shadow
            ):
                ui.label("Query Details").classes(
                    'text-xl font-semibold mb-4 text-gray-800 dark:text-gray-100' # Adjusted title styling
                )
                
                # Process query for display: strip overall, handle multi-line indentation, and replace backticks with single quotes
                original_query = query_data['query'].strip().replace('`', "'")
                lines = original_query.split('\n')
                if len(lines) > 1:
                    processed_lines = [lines[0]]
                    for line in lines[1:]:
                        stripped_line = line.lstrip()
                        if len(line) > len(stripped_line):
                            processed_lines.append('\t' + stripped_line)
                        else:
                            processed_lines.append(line)
                    query_to_display = '\n'.join(processed_lines)
                else:
                    query_to_display = original_query

                ui.code(query_to_display).classes(
                    'w-full text-xs bg-gray-100 dark:bg-gray-700 p-3 rounded-md max-h-72 overflow-y-auto font-mono border border-gray-300 dark:border-gray-600'
                )

                # Conditional display of parameters
                if query_data.get('queryParams'):
                    try:
                        query_params_str = json.dumps(query_data['queryParams'], indent=2)
                    except Exception:
                        query_params_str = str(query_data['queryParams']) # Fallback
                    ui.code(query_params_str).classes(
                        'w-full text-xs bg-gray-100 dark:bg-gray-700 p-3 rounded-md max-h-48 overflow-y-auto font-mono border border-gray-300 dark:border-gray-600'
                    )
                
                ui.button('Close', on_click=dialog.close).props('color=primary flat').classes(
                    'mt-6 self-end text-primary-500 dark:text-primary-400 hover:bg-gray-100 dark:hover:bg-gray-700 px-4 py-2 rounded-md'
                )
            dialog.open()

        def disconnect_ws():
            global ws_connection, connected_username
            if ws_connection:
                try:
                    ws_connection.close()
                    add_terminal_message("Manually disconnected", "info")
                except Exception as e:
                    error_msg = f"Error disconnecting: {str(e)}"
                    add_terminal_message(error_msg, "error")
                    ui.notify(error_msg, color="negative")
                finally:
                    ws_connection = None
                    connected_username = None
                    status_image.set_source('dave_disconnected.png')
                    # Only set status label to "Disconnected"
                    status_label.text = "Disconnected"
                    update_ui_state()

        def on_login_click():
            global connected_username, ws_connection
            # username = username_input.value
            # password = password_input.value
            username = "admin"
            password = "adminPass"

            if ws_connection:
                add_terminal_message("Already connected. Disconnect first if needed.", "info")
                return

            if not username or not password:
                status_label.text = "Please enter username and password"
                add_terminal_message("Login failed: Missing username or password", "error")
                ui.notify("Please enter username and password", color="warning")
                return

            ws_url = "ws://localhost:8000/dave-router-wss"  # Change to wss://... in production
            status_label.text = "Connecting..."
            add_terminal_message(f"Connecting to {ws_url} as {username}...", "info")
            status_image.set_source('dave_disconnected.png')  # Ensure disconnected image while connecting

            # Start WebSocket in a thread
            threading.Thread(
                target=ws_thread,
                args=(ws_url, username, password),
                daemon=True
            ).start()
            
        def update_ui_state():
            # Update UI elements based on connection state
            if ws_connection and connected_username:
                # Connected state
                username_input.disabled = True
                password_input.disabled = True
                login_button.visible = False
                disconnect_button.visible = True
                disconnect_button.text = f'Disconnect'
                connection_status.classes('bg-green-500', remove='bg-red-500')
                connection_status.text = f'Connected'
            else:
                # Disconnected state
                username_input.disabled = False
                password_input.disabled = False
                login_button.visible = True
                disconnect_button.visible = False
                connection_status.classes('bg-red-500', remove='bg-green-500')
                connection_status.text = 'Disconnected'
        
        # Set initial UI state
        update_ui_state()

        def check_messages():
            """Check for messages from the websocket thread and update UI"""
            updated = False
            while not message_queue.empty():
                msg_obj = message_queue.get()
                msg_type = msg_obj.get("type", "normal")
                message = msg_obj.get("message", "")
                if msg_type == "connected":
                    status_label.text = f"Connected as {connected_username}"
                    status_image.set_source('dave_connected.png')
                    update_ui_state()
                    add_terminal_message(message, "success")
                elif msg_type == "disconnected":
                    status_label.text = "Disconnected"
                    status_image.set_source('dave_disconnected.png')
                    update_ui_state()
                    add_terminal_message(message, "error")
                elif msg_type == "login_failed":
                    status_label.text = "Disconnected"
                    status_image.set_source('dave_disconnected.png')
                    ui.notify(message, color='negative')
                    update_ui_state()
                    add_terminal_message(message, "error")
                elif msg_type == "sql_success":
                    add_terminal_message(message, "success")
                elif msg_type == "sql_error":
                    add_terminal_message(message, "error")
                elif msg_type == "sql_execution_info":
                    add_terminal_message(msg_obj, "sql_query")
                else:
                    add_terminal_message(message, "info" if msg_type == "info" else "normal")
                updated = True
            if pending_terminal_messages:
                flush_terminal_messages()

        # Set up a timer to check for messages from the WebSocket thread
        ui.timer(0.5, check_messages)

# Run the NiceGUI app
def main():
    create_ui()
    ui.run(title='Dave Router', port=8180, favicon="https://cdn-icons-png.flaticon.com/128/6584/6584942.png")

# Helper to convert values to JSON-serializable types
def convert_json_safe(val):
    if isinstance(val, bytes):
        try:
            return val.decode('utf-8')
        except UnicodeDecodeError:
            if len(val) == 1:
                return int.from_bytes(val, 'little')
            return val.hex()
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, decimal.Decimal):
        return str(val)
    return val

if __name__ in {"__main__", "__mp_main__"}:
    main() 