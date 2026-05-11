import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import PlayerBar from './PlayerBar';

export default function MainLayout() {
  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
      <PlayerBar />
    </div>
  );
}
