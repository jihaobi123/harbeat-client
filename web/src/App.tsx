import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import LoginPage from './components/LoginPage';
import MixLabPage from './components/MixLabPage';
import MixtapePage from './components/MixtapePage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MixLabPage />} />
        <Route path="/mix-lab" element={<MixLabPage />} />
        <Route path="/mixtape" element={<MixtapePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
