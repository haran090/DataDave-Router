import json
import threading
import asyncio
import websocket
from nicegui import ui, app
from queue import Queue
import time
import sqlalchemy

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
            print(f"Received message: {msg}")
            # Try to parse as JSON for tunnel mode
            try:
                data = json.loads(msg)
                if data.get("type") == "sql-query":
                    # Execute the test connection
                    message_queue.put({"type": "info", "message": f"Executing query: {data.get('query', '')}"})
                    success, message, tables = execute_test_connection(
                        data["connectionObject"], data.get("query", "SELECT 1")
                    )
                    # NEW: Add SQL result message
                    if success:
                        # Simulate row count (since SELECT 1 returns 1 row)
                        row_count = 1  # You may want to actually fetch and count rows for real queries
                        message_queue.put({"type": "sql_success", "message": f"SQL Success: {row_count} row(s) returned."})
                    else:
                        message_queue.put({"type": "sql_error", "message": f"SQL Error: {message}"})
                    response = {
                        "type": "sql-query-result",
                        "request_id": data.get("request_id"),
                        "success": success,
                        "message": message,
                        "tables": tables
                    }
                    ws.send(json.dumps(response))
                    continue
            except Exception:
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
                    connection_status = ui.label('Disconnected').classes('text-sm rounded px-2 py-1 bg-red-500')
                    ui.label('|').classes('mx-2 text-gray-500')
                    message_count = ui.label('Messages: 0').classes('text-sm')
                    terminal_container = ui.scroll_area().classes('w-full h-full terminal-container flex-grow')

        # Store message history
        message_history = []
                    
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
            
        def add_terminal_message(text, type="normal"):
            """Add a message to the terminal with timestamp"""
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            
            # Insert at the beginning for reverse order
            message_history.insert(0, (timestamp, text, type))
            
            # Clear and re-render all messages in reverse order (newest first)
            terminal_container.clear()
            for ts, msg, msg_type in message_history:
                with terminal_container:
                    with ui.row().classes('terminal-message w-full'):
                        ui.label(f"[{ts}]").classes('terminal-time')
                        msg_class = f"terminal-{msg_type}" if msg_type in ["success", "error", "info"] else ""
                        ui.label(msg).classes(f'flex-grow {msg_class}')
            
            # Update message count
            message_count.text = f"Messages: {len(message_history)}"
            
            # Scroll to top (since newest is at the top)
            ui.run_javascript("""
                document.querySelector('.terminal').scrollTop = 0;
            """)
            
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
            if not message_queue.empty():
                msg_obj = message_queue.get()
                # msg_obj is now a dict: {"type": ..., "message": ...}
                msg_type = msg_obj.get("type", "normal")
                message = msg_obj.get("message", "")

                # Only update the status label for connection/disconnection
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
                else:
                    # All other messages go to the terminal only
                    add_terminal_message(message, "info" if msg_type == "info" else "normal")

        # Set up a timer to check for messages from the WebSocket thread
        ui.timer(0.5, check_messages)

# Run the NiceGUI app
def main():
    create_ui()
    ui.run(title='Dave Router', port=8180)

if __name__ in {"__main__", "__mp_main__"}:
    main() 