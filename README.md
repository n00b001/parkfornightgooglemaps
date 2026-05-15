# Park4Night Google Maps - PWA

A modern progressive web app that replicates Park4Night functionality with deep Google Maps integration, providing a user-friendly interface for finding, rating, and managing campsites and parking spots.

## Features

- **Progressive Web App (PWA)**: Installable on mobile and desktop with offline support
- **Google Maps Integration**: Deep integration with Google Maps for location-based services
- **Google Authentication**: Sign in with your Google account
- **Offline Capabilities**: Cache parking data locally for offline access
- **Advanced Search**: Filter, sort, and search parking spots by various criteria
- **User Favorites**: Save and manage your favorite parking locations
- **Reviews & Ratings**: Read and write reviews for parking spots
- **GPS Tracking**: Automatically record visited locations based on GPS
- **Easy Point Addition**: Add parking spots directly to your Google Maps account
- **Responsive Design**: Works seamlessly on mobile, tablet, and desktop

## Tech Stack

### Frontend
- React 18+ with TypeScript
- Vite for fast development and optimized builds
- Google Maps API
- Service Workers for offline functionality
- IndexedDB for local data persistence
- Tailwind CSS for styling
- React Query for data synchronization

### Backend
- Node.js + Express
- MongoDB for data persistence
- JWT authentication
- Passport.js for Google OAuth
- RESTful API with real-time updates

### Hosting & Deployment
- Render.com for both frontend and backend
- Automated CI/CD pipeline

## Getting Started

### Prerequisites
- Node.js 18+
- npm or yarn
- MongoDB Atlas account
- Google Cloud Console account (for Maps API and OAuth)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/n00b001/parkfornightgooglemaps.git
   cd parkfornightgooglemaps
   ```

2. **Install dependencies**
   ```bash
   npm run install:all
   ```

3. **Configure environment variables**
   - Create `.env` files in both `server` and `client` directories
   - See `.env.example` files for required variables

4. **Start development servers**
   ```bash
   npm run dev
   ```

5. **Build for production**
   ```bash
   npm run build
   ```

## Project Structure

```
.
├── server/                 # Node.js Express backend
│   ├── src/
│   │   ├── api/           # API routes
│   │   ├── models/        # MongoDB schemas
│   │   ├── services/      # Business logic
│   │   ├── middleware/    # Auth & utilities
│   │   ├── config/        # Configuration
│   │   └── index.js       # App entry point
│   ├── .env.example
│   └── package.json
├── client/                # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── hooks/         # Custom React hooks
│   │   ├── pages/         # Page components
│   │   ├── services/      # API clients
│   │   ├── store/         # State management
│   │   ├── utils/         # Utilities
│   │   ├── index.css      # Global styles
│   │   ├── App.tsx        # Main app component
│   │   └── main.tsx       # Entry point
│   ├── public/            # Static files & PWA manifest
│   ├── .env.example
│   └── package.json
├── .gitignore
├── package.json           # Root package.json for scripts
└── README.md
```

## Deployment on Render

### Backend Service
1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set build command: `npm run build:server`
4. Set start command: `npm run start:server`
5. Add environment variables from `.env.example`

### Frontend Service (Static Site)
1. Create a new Static Site on Render
2. Connect your GitHub repository
3. Set build command: `npm run build:client`
4. Set publish directory: `client/dist`

## API Documentation

See `server/API.md` for detailed API endpoint documentation.

## Contributing

Contributions are welcome! Please create a feature branch and submit a pull request.

## License

MIT
