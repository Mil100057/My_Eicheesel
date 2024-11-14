HELP WANTED
If you want to contribute please contact me.
Application still in debug mode

![img.png](img.png)

# Eicheesel 🐿️

A savings and long-term investment simulation application by Mil100057

```
     /\___/\
    (  o o  )
    (  =^=  ) 
     (____))
    /      \
```

## Disclaimer

⚠️ Please read carefully:
- This application is for testing and simulation purposes only
- No guarantees are provided regarding calculation results
- You are responsible for your data security
- The application only performs basic calculations and storage
- No financial advice is provided

## Quick Start

### Prerequisites
- Docker
- Docker Daemon running
- In settings.py add:
SECRET_KEY = '*your django key here*'
ALPHA_VANTAGE_API_KEY = '*your API key here*'
ALLOWED_HOST [*your host if not local*]

### Installation

1. Build the Docker container:
```bash
docker compose build
```

2. Start the application:
```bash
docker compose up
```

### Accessing the Application

- URL: `http://localhost:8000`
- 
⚠️⚠️⚠️⚠️NOTE : in this version , No super User created, you have to create a normal user⚠️⚠️⚠️⚠️⚠️

### Please signup first as admin
- Username: `admin`
- Password: `your_password`

⚠️ **Important**: Change these credentials on first login!

⚠️⚠️⚠️⚠️NOTE : in this version , No super User created, you have to create a normal user⚠️⚠️⚠️⚠️⚠️

## Administration

- Admin panel available at: `http://localhost:8000/admin/`
- Use this interface to manage credentials and access the database

## Usage Guide

### Initial Setup
1. **Clear Example Data** (Optional)
   - Navigate to "Vue par nom" in the sidebar
   - Delete existing simulation data if desired

2. **Configure Categories**
   - Go to Settings → Catégorie(s) in the sidebar
   - Select or create categories for your simulations

3. **Start Simulating**
   - Click "Ajouter une simulation" to begin a new simulation

### Customizing Categories

To modify category types:
1. Navigate to the `simulation` folder
2. Edit `models.py`
3. Modify the `Category` class as needed

## Support

For issues or questions, please create an issue in the repository.

---

Made with ❤️ by Mil100057
