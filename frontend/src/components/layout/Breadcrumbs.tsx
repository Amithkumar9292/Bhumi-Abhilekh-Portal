import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';

export interface Crumb {
  label: string;
  href?: string;
}

interface BreadcrumbsProps {
  crumbs: Crumb[];
}

export function Breadcrumbs({ crumbs }: BreadcrumbsProps) {
  if (crumbs.length === 0) return null;

  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <Link to="/dashboard" className="breadcrumbs__item" aria-label="Home">
        <Home size={12} />
      </Link>
      {crumbs.map((crumb, i) => (
        <React.Fragment key={i}>
          <ChevronRight className="breadcrumbs__separator" size={12} aria-hidden="true" />
          {crumb.href && i < crumbs.length - 1 ? (
            <Link to={crumb.href} className="breadcrumbs__item">
              {crumb.label}
            </Link>
          ) : (
            <span className="breadcrumbs__item breadcrumbs__item--current" aria-current="page">
              {crumb.label}
            </span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
