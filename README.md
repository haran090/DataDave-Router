# 🚀 Dave Tunnel Mode Router

![Dave Router Banner](dave_connected.png)

Want to use [Data Dave](https://data-dave.xyz) on a database behind a firewall? 
Do you need VPN or LAN access to your database? Easily connect Dave to route SQL queries securely via WebSocket through your machine.

---

## ✨ Features

- **Tunnel Mode**: Securely route SQL queries via WebSocket.
- **Live Terminal**: Real-time message queue and status updates.
- **Built For Ease**: A few taps and clicks, that's it. 

---

## 🖥️ Quick Start

### 1. Download & Run

#### Option A: Python Script

1. **Clone the repo:**
   ```bash
   git clone https://github.com/yourusername/dave-router.git
   cd dave-router
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app:**
   ```bash
   python dave_router.py
   ```

4. **Open your browser:**  
   Go to [http://localhost:8180](http://localhost:8180)

#### Option B: Download Executable

- **[Download for Windows](https://github.com/yourusername/dave-router/releases/latest/download/dave-router.exe)**
- **[Download for MacOS](https://github.com/yourusername/dave-router/releases/latest/download/dave-router.app)**

Just double-click to launch!

---

## 🛠️ How It Works

- **Login** with your credentials.
- The app establishes a **WebSocket** connection to your backend.
- Send SQL queries and receive results in real-time.
- All activity is logged in the **terminal panel** for transparency.

![Screenshot](dave_connected.png)

---

## ⚡ Packaging as an Executable

Want to build your own `.exe` or `.app`?

```bash
pip install pyinstaller
pyinstaller --onefile dave_router.py
```
- The output will be in the `dist/` folder.

---

## 🤝 Contributing

Pull requests, issues, and suggestions are welcome!  
Let's make database tunneling easy and beautiful for everyone.

---

## 📄 License

MIT License

---

> Made with ❤️ by the Data Dave team