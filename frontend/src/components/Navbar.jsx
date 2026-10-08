import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { LayoutDashboard, FileText, Target, Map, MessagesSquare, LogOut, GraduationCap } from 'lucide-react';

export default function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const navItems = [
    { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/resume', icon: FileText, label: 'Resume' },
    { path: '/gap', icon: Target, label: 'Skill Gap' },
    { path: '/roadmap', icon: Map, label: 'Roadmap' },
    { path: '/interview', icon: MessagesSquare, label: 'Interview' },
  ];

  return (
    <nav className="bg-white border-b border-gray-100 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center gap-2">
            <div className="bg-brand-500 text-white p-2 rounded-lg">
              <GraduationCap size={24} />
            </div>
            <span className="font-bold text-xl tracking-tight text-gray-900">PlaceIQ</span>
          </div>
          
          <div className="hidden md:flex space-x-1 items-center">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link key={item.path} to={item.path} className="relative px-3 py-2 rounded-md text-sm font-medium transition-colors">
                  {isActive ? (
                    <span className="text-brand-600 flex items-center gap-2">
                      <Icon size={18} /> {item.label}
                      <motion.div layoutId="underline" className="absolute left-0 right-0 bottom-0 h-0.5 bg-brand-500 rounded-full" />
                    </span>
                  ) : (
                    <span className="text-gray-500 hover:text-gray-900 hover:bg-gray-50 flex items-center gap-2 px-2 py-1 rounded-md transition-all">
                      <Icon size={18} /> {item.label}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          <div className="flex items-center">
            <button onClick={handleLogout} className="text-gray-400 hover:text-red-500 transition-colors p-2 rounded-full hover:bg-red-50">
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}