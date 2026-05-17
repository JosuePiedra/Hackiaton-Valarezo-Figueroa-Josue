import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AppHeader } from './components/layout/AppHeader';
import { LandingPage } from './pages/LandingPage';
import { AdminPage } from './pages/AdminPage';

function App() {
  return (
    <Router>
      <div className="min-h-screen flex flex-col">
        <AppHeader />
        <main className="flex-1 flex flex-col">
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
