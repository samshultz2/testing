# PosyHub Student Management System

A comprehensive student management system built with Python Flask for Nigerian secondary schools.

## Features

- **Student Management**: Add, edit, view, and delete students with full details
- **Parent Contacts**: Multiple contact numbers per student
- **Academic Structure**: Sessions, Terms, Classes, and Arms management
- **Attendance Tracking**: Daily, weekly, and termly attendance with automatic calculations
- **WAEC Results**: Enter and analyze WAEC examination results
- **JAMB Results**: Track JAMB scores with statistics
- **Import/Export**: Excel import/export functionality
- **Charts & Reports**: Visual analytics and comprehensive reports

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and go to: `http://localhost:5000`

## Login

- **Password**: `posyhubcomng`

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: HTML, CSS, JavaScript
- **Charts**: Chart.js
- **Excel**: openpyxl

## Project Structure

```
student_management/
├── app.py              # Main application
├── config.py           # Configuration
├── requirements.txt    # Dependencies
├── models/             # Database models
├── routes/             # Route handlers
├── templates/          # HTML templates
├── static/             # CSS, JS, images
├── utils/              # Helper functions
└── instance/           # Database file
```

## Usage

1. **Setup Academic Year**: Create session → Add terms → Generate weeks
2. **Setup Classes**: Add classes → Add arms → Create class-arm assignments
3. **Add Students**: Register students → Enroll in classes
4. **Mark Attendance**: Select class → Select date → Mark present/absent
5. **Enter Results**: Add WAEC/JAMB results per student
6. **View Reports**: Check statistics, charts, and export data

## License

© 2024 PosyHub. All rights reserved.
