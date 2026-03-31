import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Signals from './pages/Signals';
import Backtests from './pages/Backtests';
import Review from './pages/Review';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Signals />} />
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/review" element={<Review />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
