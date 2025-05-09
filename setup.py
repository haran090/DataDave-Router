# setup.py
from cx_Freeze import setup, Executable

# Replace with your script name and metadata
setup(
    name="DaveRouter",
    version="1.0",
    description="Compiled python app to use for tunnel mode with Data Dave",
    executables=[Executable("dave_router.py")],
)

