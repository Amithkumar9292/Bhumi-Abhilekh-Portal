import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, FileText, Users, Settings, BookOpen,
  MapPin, ClipboardCheck, BarChart2,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

interface NavItem {
  label: string;
  labelHi: string;
  href: string;
  icon: React.ReactNode;
  roles?: string[];
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Dashboard',
    labelHi: 'डैशबोर्ड',
    href: '/dashboard',
    icon: <LayoutDashboard size={15} />,
  },
  {
    label: 'Land Records',
    labelHi: 'भूमि अभिलेख',
    href: '/land-records',
    icon: <FileText size={15} />,
  },
  {
    label: 'Verification',
    labelHi: 'सत्यापन',
    href: '/verification',
    icon: <ClipboardCheck size={15} />,
    roles: ['ADMIN', 'VERIFIER'],
  },
  {
    label: 'Documents',
    labelHi: 'दस्तावेज़',
    href: '/documents',
    icon: <BookOpen size={15} />,
  },
  {
    label: 'Map View',
    labelHi: 'मानचित्र',
    href: '/map',
    icon: <MapPin size={15} />,
  },
  {
    label: 'Reports',
    labelHi: 'रिपोर्ट',
    href: '/reports',
    icon: <BarChart2 size={15} />,
    roles: ['ADMIN', 'OFFICER'],
  },
  {
    label: 'Admin',
    labelHi: 'प्रशासन',
    href: '/admin',
    icon: <Users size={15} />,
    roles: ['ADMIN'],
  },
];

interface NavBarProps {
  language?: 'en' | 'hi';
}

export function NavBar({ language = 'en' }: NavBarProps) {
  const { user } = useAuthStore();

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (!item.roles) return true;
    if (!user) return false;
    return item.roles.includes(user.role);
  });

  return (
    <nav className="primary-nav" role="navigation" aria-label="Primary navigation">
      {visibleItems.map((item) => (
        <NavLink
          key={item.href}
          to={item.href}
          className={({ isActive }) =>
            `primary-nav__item${isActive ? ' active' : ''}`
          }
          aria-current={undefined}
        >
          {item.icon}
          <span>{language === 'hi' ? item.labelHi : item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
