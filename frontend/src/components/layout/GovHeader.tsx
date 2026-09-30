import React, { useState, useRef, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Upload, FileText, MapPin, ClipboardCheck,
  Map, AlertTriangle, BarChart2, History, Users, Plug, Settings,
  Bell, Search, ChevronDown, LogOut, User, ShieldCheck, Zap,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUIStore } from '../../store/uiStore';
import { LanguageSelector } from '../shared/LanguageSelector';
import { useTranslation } from '../../i18n/useTranslation';

type NavKey = 'nav.dashboard'|'nav.intake'|'nav.pipeline'|'nav.documents'|'nav.landRecords'|'nav.verification'|'nav.gisMap'|'nav.anomalies'|'nav.reports'|'nav.auditTrail'|'nav.users'|'nav.integrations'|'nav.settings';

const NAV: { to: string; key: NavKey; icon: React.ReactNode; roles?: string[] }[] = [
  { to: '/dashboard',    key: 'nav.dashboard',   icon: <LayoutDashboard size={14}/> },
  { to: '/intake',       key: 'nav.intake',       icon: <Upload size={14}/> },
  { to: '/pipeline',     key: 'nav.pipeline',     icon: <Zap size={14}/> },
  { to: '/documents',    key: 'nav.documents',    icon: <FileText size={14}/> },
  { to: '/land-records', key: 'nav.landRecords',  icon: <MapPin size={14}/> },
  { to: '/verification', key: 'nav.verification', icon: <ClipboardCheck size={14}/> },
  { to: '/map',          key: 'nav.gisMap',       icon: <Map size={14}/> },
  { to: '/anomalies',    key: 'nav.anomalies',    icon: <AlertTriangle size={14}/> },
  { to: '/reports',      key: 'nav.reports',      icon: <BarChart2 size={14}/> },
  { to: '/audit',        key: 'nav.auditTrail',   icon: <History size={14}/> },
  { to: '/users',        key: 'nav.users',        icon: <Users size={14}/>, roles: ['ADMIN'] },
  { to: '/integrations', key: 'nav.integrations', icon: <Plug size={14}/>, roles: ['ADMIN'] },
  { to: '/settings',     key: 'nav.settings',     icon: <Settings size={14}/> },
];

// Notifications are now sourced from uiStore

export function GovHeader() {
  const { user, clearAuth } = useAuthStore();
  const { notifications, markAllRead } = useUIStore();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [notifOpen, setNotifOpen] = useState(false);
  const [userOpen, setUserOpen]   = useState(false);
  const [search, setSearch]       = useState('');
  const notifRef = useRef<HTMLDivElement>(null);
  const userRef  = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function close(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
      if (userRef.current  && !userRef.current.contains(e.target as Node))  setUserOpen(false);
    }
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const initials = user?.full_name?.split(' ').map(w => w[0]).join('').slice(0,2) ?? 'U';
  const unread = notifications.filter(n => !n.read).length;

  return (
    <>
      {/* Tri-color top strip */}
      <div style={{ height:3, background:'linear-gradient(to right,#FF9933 33.3%,white 33.3% 66.6%,#138808 66.6%)', position:'sticky', top:0, zIndex:600 }}/>

      {/* Gov top bar */}
      <div className="gov-topbar">
        <div className="gov-topbar__emblem">
          <span style={{fontSize:13,marginRight:6}}>🏛</span>
          Government of India — Ministry of Rural Development
        </div>
        <div className="gov-topbar__right">
          <span className="demo-badge">⚠ DEMO SYSTEM</span>
          <a href="#" className="gov-topbar__link">Screen Reader</a>
          <a href="#" className="gov-topbar__link">Skip to Content</a>
        </div>
      </div>

      {/* Main header */}
      <header className="gov-header">
        <div className="gov-header__brand">
          <div className="gov-header__logo">
            <ShieldCheck size={18} color="rgba(255,255,255,0.9)"/>
          </div>
          <div>
            <div className="gov-header__title">Bhumi Abhilekh Portal</div>
            <div className="gov-header__subtitle">Land Record Digitization System</div>
          </div>
        </div>
        <div className="gov-header__sep"/>

        {/* Search */}
        <div className="gov-header__search">
          <div className="g-search">
            <Search size={13} className="g-search__icon"/>
            <input
              className="g-search__input"
              placeholder="Search khasra no., owner, district…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <div className="g-search__kbd">
              <span className="kbd">Ctrl</span><span className="kbd">K</span>
            </div>
          </div>
        </div>

        <div className="gov-header__actions">
          {/* Lang selector */}
          <LanguageSelector />

          {/* Notifications */}
          <div style={{position:'relative'}} ref={notifRef}>
            <button className="icon-btn" onClick={()=>{setNotifOpen(o=>!o);setUserOpen(false);}}>
              <Bell size={15}/>
              {unread > 0 && <span className="icon-btn__badge"/>}
            </button>
            {notifOpen && (
              <div className="notif-panel">
                <div className="notif-panel__hdr">
                  <span className="notif-panel__title">Notifications {unread > 0 && <span style={{fontSize:10,background:'var(--color-saffron-500)',color:'white',borderRadius:8,padding:'1px 5px',marginLeft:4}}>{unread}</span>}</span>
                  <button style={{fontSize:11,color:'var(--color-navy-700)',background:'none',border:'none',cursor:'pointer'}} onClick={() => markAllRead()}>Mark all read</button>
                </div>
                {notifications.slice(0, 5).map(n => (
                  <div key={n.id} className={`notif-item${!n.read?' notif-item--unread':''}`}>
                    <div className="notif-item__icon" style={{background: n.type === 'success' ? '#ECFDF5' : n.type === 'warning' ? '#FEF3C7' : n.type === 'error' ? '#FEF2F2' : '#EFF6FF'}}/>
                    <div className="notif-item__body">
                      <div className="notif-item__title">{n.title}</div>
                      <div className="notif-item__desc">{n.description}</div>
                    </div>
                    <div className="notif-item__time">{new Date(n.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
                  </div>
                ))}
                <div style={{padding:'10px 16px',textAlign:'center'}}>
                  <button onClick={() => { navigate('/audit'); setNotifOpen(false); }} style={{fontSize:12,color:'var(--color-navy-700)',background:'none',border:'none',cursor:'pointer'}}>View all notifications →</button>
                </div>
              </div>
            )}
          </div>

          {/* User menu */}
          <div className="user-menu" ref={userRef}>
            <button className="user-menu__trigger" onClick={()=>{setUserOpen(o=>!o);setNotifOpen(false);}}>
              <div className="user-menu__avatar">{initials}</div>
              <span>{user?.full_name?.split(' ')[0]}</span>
              <ChevronDown size={12} style={{opacity:0.6}}/>
            </button>
            {userOpen && (
              <div className="user-menu__dropdown">
                <div className="user-menu__header">
                  <div className="user-menu__name">{user?.full_name}</div>
                  <div className="user-menu__email">{user?.email}</div>
                  <span className={`role-badge role-badge--${user?.role}`} style={{marginTop:6}}>{user?.role}</span>
                </div>
                <div style={{paddingTop:4,paddingBottom:4}}>
                  <button className="user-menu__item" onClick={()=>{setUserOpen(false);navigate('/settings');}}>
                    <User size={13}/> My Profile
                  </button>
                  <button className="user-menu__item" onClick={()=>{setUserOpen(false);navigate('/settings');}}>
                    <Settings size={13}/> {t('settings.title')}
                  </button>
                  <div className="user-menu__sep"/>
                  <button className="user-menu__item user-menu__item--danger"
                    onClick={()=>{ clearAuth(); navigate('/login'); }}>
                    <LogOut size={13}/> {t('auth.logout')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Primary Nav */}
      <nav className="primary-nav">
        {NAV.filter(n => !n.roles || n.roles.includes(user?.role ?? '')).map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({isActive}) => `nav-item${isActive ? ' active' : ''}`}
          >
            <span className="nav-item__icon">{item.icon}</span>
            {t(item.key)}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
