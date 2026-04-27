# IoT Data Aggregation - Frontend

A professional, modern, eye-catching futuristic frontend dashboard for the IoT Data Aggregation system. Built with vanilla HTML5, CSS3, and JavaScript - no framework dependencies!

## 🎨 Features

### Dashboard Section
- **Real-time Statistics**: View total submissions, processing count, completed tasks, and failed jobs
- **Status Distribution Chart**: Doughnut chart showing breakdown of submission statuses
- **Submissions Timeline**: Line chart with hourly submission trends
- **Recent Activity Feed**: Live updates of submissions with timestamps and status indicators

### Submit Data Section
- **Flexible Data Input**:
  - Manual entry with comma-separated values
  - CSV/JSON file upload support
  - Drag-and-drop file upload
- **Data Preview**: Real-time preview of statistics (Min, Max, Avg)
- **Form Validation**: Client-side validation with helpful error messages
- **Submission Result**: Clear success/error feedback with data IDs

### Analytics Section
- **Summary Cards**: Grid of processed summaries with statistics
- **Search by Data ID**: Quick lookup for specific submissions
- **Summary Display**: Min, Max, Average, and Count for each dataset

### History Section
- **Data Table**: Comprehensive view of all submissions
- **Status Filtering**: Filter submissions by status (Pending, Processing, Done, Failed)
- **Summary Details**: Summary statistics inline in the table
- **Export to CSV**: Download historical data for analysis
- **Detail View**: Quick navigation to analytics for any submission

## 🎯 Design Highlights

### Color Scheme (Futuristic Dark Theme)
- **Primary**: Cyan (#00d4ff) - Main interactive elements
- **Secondary**: Purple (#7c3aed) - Accent elements
- **Accent**: Pink (#ff0099) - highlights
- **Status Colors**:
  - Pending: Amber (#f59e0b)
  - Processing: Cyan (#00d4ff)
  - Done: Green (#10b981)
  - Failed: Red (#ef4444)

### Visual Features
- Glassmorphism effects with backdrop blur
- Gradient backgrounds and borders
- Glowing shadows and hover states
- Smooth animations and transitions
- Responsive grid layouts
- Professional typography hierarchy

## 🚀 Getting Started

### Prerequisites
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Backend API running via Docker Compose (or reachable from browser)

### Installation

1. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

2. **Open in browser** (if using local file serving):
   ```bash
   # Option 1: Using Python
   python -m http.server 8000
   
   # Option 2: Using Node.js
   npx http-server
   
   # Option 3: Using VS Code Live Server extension
   ```

3. **Visit in browser**:
   ```
   http://localhost:8000
   ```

### Docker Setup
The frontend is served via Docker Compose with the backend:

```bash
docker compose up --build
```

Access at: `http://localhost:8080`

The frontend uses `/api` and is proxied to the API service by Nginx.

## 📁 File Structure

```
frontend/
├── index.html          # Main HTML structure
├── styles.css          # Complete styling (2000+ lines)
├── app.js              # Application logic (800+ lines)
├── README.md           # This file
└── assets/
    └── (future: icons, images, etc.)
```

## 🔧 Configuration

### API Settings
Edit the API base URL in `app.js`:

```javascript
const API_BASE_URL = window.IOT_API_BASE_URL || '/api';
const AUTO_REFRESH_INTERVAL = 5000; // milliseconds
```

### Auto-refresh
- Toggle via the "Auto" checkbox in the navbar
- Default interval: 5 seconds
- Can be changed in `AUTO_REFRESH_INTERVAL` constant

## 📊 API Integration

### Endpoints Used
The frontend connects to these backend endpoints:

#### 1. GET `/list`
Returns list of all submissions with their current status

**Response Format**:
```json
{
  "data": [
    {
      "data_id": "uuid",
      "sensor_id": "SENSOR-01",
      "object_key": "raw/SENSOR-01/uuid.json",
      "status": "done|pending|processing|failed",
      "summary": {
        "min": 20.5,
        "max": 25.3,
        "avg": 22.4,
        "count": 10
      },
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### 2. POST `/data`
Submit new sensor data for processing

**Request Body**:
```json
{
  "sensor_id": "SENSOR-01",
  "values": [20.5, 21.3, 22.1]
}
```

**Response**:
```json
{
  "data_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

#### 3. GET `/summary?id={data_id}`
Get summary statistics for a specific submission

**Response**:
```json
{
  "data_id": "uuid",
  "sensor_id": "SENSOR-01",
  "status": "done",
  "summary": {
    "min": 20.5,
    "max": 25.3,
    "avg": 22.4,
    "count": 10
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## 🎮 Manual Testing

### Test Data Entry
1. **Navigate to Submit Data**
2. **Sensor ID**: `TEMP-ZONE-A`
3. **Values**: `20.5, 21.2, 22.1, 21.8, 20.9`
4. **Click Submit Data**

### Test File Upload
1. **Create test CSV** (`test_data.csv`):
   ```
   20.5
   21.2
   22.1
   21.8
   20.9
   ```

2. **Or test JSON** (`test_data.json`):
   ```json
   [20.5, 21.2, 22.1, 21.8, 20.9]
   ```

3. **Select file and submit**

### Monitor Progress
- Dashboard shows status in real-time
- Watch for "Processing" status change to "Done"
- Summary statistics appear after processing

## 🛠️ Development

### Project Structure (app.js)
```
- Configuration & Global State
- DOM Initialization & Event Listeners
- Section Navigation
- Dashboard Logic
- Submit Data Logic
- Analytics Logic
- History Logic
- API Utilities
- Auto-refresh Logic
- UI Helpers & Utilities
```

### Key Functions

**Navigation**:
- `switchToSection(sectionId)` - Changes active section

**Data Loading**:
- `loadDashboardData()` - Fetch and render dashboard
- `loadAnalyticsData()` - Load completed submissions
- `loadHistoryData()` - Load full history with filters

**Charts (Chart.js)**:
- `renderStatusChart()` - Doughnut chart
- `renderSubmissionsChart()` - Line chart

**Utilities**:
- `fetchFromAPI()` - Centralized API calls
- `showToast()` - Notifications
- `formatTime()` - Relative timestamps
- `truncateId()` - ID shortening

### Adding New Features

1. **Add new section**:
   ```html
   <section id="new-section" class="section">
     <!-- content -->
   </section>
   ```

2. **Add navigation button**:
   ```html
   <button class="nav-link" data-section="new-section">New</button>
   ```

3. **Add loading function**:
   ```javascript
   function loadNewSectionData() {
     // fetch and render
   }
   ```

4. **Update switch statement**:
   ```javascript
   case 'new-section':
     loadNewSectionData();
     break;
   ```

## 🌐 Browser Support

- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- IE 11: ❌ Not supported (uses modern CSS/JS)

## 📱 Responsive Design

Breakpoints:
- **Desktop**: 1024px+
- **Tablet**: 768px - 1024px
- **Mobile**: Below 768px

All charts and tables automatically reflow for mobile viewing.

## 🔒 Security Considerations

- **CORS**: Ensure backend allows requests from frontend origin
- **Input Validation**: Frontend validates before sending to API
- **Error Handling**: Errors gracefully displayed without exposing system details
- **No Credentials**: Currently no authentication (add as needed)

### Adding CORS Support
If running frontend on different domain, add to Flask app:

```python
from flask_cors import CORS
CORS(app)
```

## 🚨 Common Issues

### Issue: CORS Error
**Solution**: Ensure backend allows CORS:
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
```

### Issue: API_BASE_URL not correct
**Solution**: Check `app.js` and update `API_BASE_URL` to match backend location

### Issue: Charts not loading
**Solution**: Ensure Chart.js CDN is loaded (check console for errors)

### Issue: File upload not working
**Solution**: Verify file is CSV/JSON with compatible data format

## 📊 Performance Tips

1. **Data Filtering**: Large datasets may slow down the table
2. **Chart Rendering**: Automatically destroys old charts to prevent memory leaks
3. **Auto-refresh**: Can be disabled for large deployments
4. **Export**: CSV export works well with 1000+ records

## 🎓 Learning Resources

- [HTML5 Semantic Elements](https://developer.mozilla.org/en-US/docs/Glossary/Semantic_HTML)
- [CSS Grid & Flexbox](https://css-tricks.com/)
- [Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API)
- [Chart.js Documentation](https://www.chartjs.org/)

## 📝 Future Enhancements

- [ ] User authentication & authorization
- [ ] Real-time WebSocket updates
- [ ] Advanced filtering and search
- [ ] Data export in multiple formats (Excel, PDF)
- [ ] Dark/Light theme toggle
- [ ] Mobile app version (React Native)
- [ ] Data visualization improvements
- [ ] Performance monitoring dashboard
- [ ] Batch operations
- [ ] Sensor configuration UI

## 📄 License

This frontend is part of the IoT Data Aggregation project.

## 👨‍💻 Developer Notes

- **Built with**: Vanilla JavaScript (no frameworks)
- **Styling**: Pure CSS3 (no preprocessor)
- **Charts**: Chart.js v4.4.0
- **Responsiveness**: Mobile-first approach
- **Accessibility**: WCAG 2.1 AA standards followed

---

**Created**: January 2026
**Last Updated**: January 2026
**Version**: 1.0.0
