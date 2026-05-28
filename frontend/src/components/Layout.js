import React from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, ClipboardCheck, Upload, LogOut, Leaf } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate('/login'); };

  const initials = user
    ? (user.first_name?.[0] || user.username[0]).toUpperCase()
    : '?';

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h2><Leaf size={14} style={{ display: 'inline', marginRight: 6 }} />BreatheESG</h2>
          <span>Emissions Data Platform</span>
        </div>

        <nav style={{ flex: 1 }}>
          <NavLink to="/dashboard" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <LayoutDashboard size={16} /> Dashboard
          </NavLink>
          <NavLink to="/review" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <ClipboardCheck size={16} /> Review Queue
          </NavLink>
          <NavLink to="/upload" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            <Upload size={16} /> Ingest Data
          </NavLink>
        </nav>

        <div className="sidebar-bottom">
          <div className="user-chip" style={{ marginBottom: 12 }}>
            <div className="user-avatar">{initials}</div>
            <div>
              <div className="user-name">{user?.first_name || user?.username}</div>
              <div className="user-role">{user?.role || 'analyst'}</div>
            </div>
          </div>
          <button className="nav-item" onClick={handleLogout}>
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
