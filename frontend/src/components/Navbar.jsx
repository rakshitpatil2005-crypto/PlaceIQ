import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowUpRight, ChevronLeft, ChevronRight, GraduationCap, LogOut,
  MoreHorizontal, Sparkles, X,
} from 'lucide-react';
import api from '../api';
import {
  getMobileMoreItems,
  getMobilePrimaryItems,
  getNavigationItems,
  isNavigationItemActive,
} from '../utils/placementDashboard';

export function MobileMoreMenu({ items, plan, onClose, onNavigate, onLogout }) {
  const closeButtonRef = useRef(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose(true);
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = Array.from(
      event.currentTarget.querySelectorAll('a[href], button:not(:disabled)'),
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="mobile-more-layer">
      <button
        type="button"
        className="mobile-more-backdrop"
        aria-label="Close navigation menu"
        onClick={() => onClose(true)}
      />
      <section
        className="mobile-more-sheet"
        id="mobile-more-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mobile-more-title"
        onKeyDown={handleKeyDown}
      >
        <div className="mobile-more-heading">
          <div>
            <p className="mobile-more-eyebrow">PlaceIQ</p>
            <h2 id="mobile-more-title">More destinations</h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="mobile-more-close"
            aria-label="Close navigation menu"
            onClick={() => onClose(true)}
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <p className="mobile-more-hint">
          Practice and assessments open from lessons, recommendations, and active learning flows.
        </p>
        <nav className="mobile-more-links" aria-label="More destinations">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`mobile-more-link ${item.active ? 'active' : ''}`}
                aria-current={item.active ? 'page' : undefined}
                onClick={onNavigate}
              >
                <span className="mobile-more-icon"><Icon size={19} aria-hidden="true" /></span>
                <span>{item.label}</span>
                <ArrowUpRight className="mobile-more-arrow" size={16} aria-hidden="true" />
              </Link>
            );
          })}
        </nav>

        <div className="mobile-more-footer">
          <div className="mobile-plan-status" aria-label={`Current plan: ${plan || 'unavailable'}`}>
            <Sparkles size={18} aria-hidden="true" />
            <span>{plan === 'premium' ? 'Premium access' : plan === 'free' ? 'Core plan' : 'Plan status unavailable'}</span>
          </div>
          <button type="button" className="mobile-logout" onClick={onLogout}>
            <LogOut size={18} aria-hidden="true" />
            <span>Log out</span>
          </button>
        </div>
      </section>
    </div>
  );
}

export default function Navbar({ collapsed, onCollapsedChange }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [plan, setPlan] = useState(null);
  const [role, setRole] = useState(null);
  const [moreOpenPath, setMoreOpenPath] = useState(null);
  const moreButtonRef = useRef(null);
  const moreOpen = moreOpenPath === location.pathname;
  const navItems = getNavigationItems(role);
  const primaryItems = getMobilePrimaryItems(role);
  const moreItems = getMobileMoreItems(role).map((item) => ({
    ...item,
    active: isNavigationItemActive(location.pathname, item.path),
  }));
  const moreIsActive = moreItems.some((item) => isNavigationItemActive(location.pathname, item.path));

  useEffect(() => {
    let active = true;
    api.get('/auth/me')
      .then(({ data }) => {
        if (active) setRole(data.role || null);
      })
      .catch((error) => {
        console.error('Unable to load the user role for placement navigation.', error);
        if (active) setRole(null);
      });
    api.get('/premium/plan')
      .then(({ data }) => {
        if (active) setPlan(data.plan === 'premium' ? 'premium' : 'free');
      })
      .catch(() => {
        if (active) setPlan(null);
      });
    return () => { active = false; };
  }, []);

  const closeMore = (restoreFocus = false) => {
    setMoreOpenPath(null);
    if (restoreFocus) {
      window.requestAnimationFrame(() => moreButtonRef.current?.focus());
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  return (
    <>
      <aside
        className={`sidebar ${collapsed ? 'collapsed' : ''}`}
        aria-label="Main navigation"
      >
        <div className="sidebar-brand">
          <span className="brand-mark"><GraduationCap size={21} aria-hidden="true" /></span>
          <div className="brand-copy">
            <div className="brand-text">PlaceIQ</div>
            <div className="brand-subtext">Career intelligence</div>
          </div>
        </div>

        <p className="sidebar-section-label">Workspace</p>
        <nav className="sidebar-nav" aria-label="Workspace">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isNavigationItemActive(location.pathname, item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`sidebar-link ${active ? 'active' : ''}`}
                aria-current={active ? 'page' : undefined}
                aria-label={item.label}
                title={collapsed ? item.label : undefined}
              >
                <span className="sidebar-link-icon"><Icon size={19} aria-hidden="true" /></span>
                <span className="sidebar-link-label">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <Link
            to="/premium"
            className="sidebar-plan"
            aria-label={`Current plan: ${plan || 'unavailable'}`}
            title={collapsed ? `Current plan: ${plan || 'unavailable'}` : undefined}
          >
            <Sparkles size={18} aria-hidden="true" />
            <span className="sidebar-bottom-label">
              {plan === 'premium' ? 'Premium access' : plan === 'free' ? 'Core plan' : 'Plan unavailable'}
            </span>
          </Link>
          <button
            type="button"
            className="sidebar-control sidebar-collapse"
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
            onClick={() => onCollapsedChange(!collapsed)}
          >
            {collapsed ? <ChevronRight size={18} aria-hidden="true" /> : <ChevronLeft size={18} aria-hidden="true" />}
            <span className="sidebar-bottom-label">{collapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span>
          </button>
          <button
            type="button"
            className="sidebar-control"
            aria-label="Logout"
            title={collapsed ? 'Logout' : undefined}
            onClick={handleLogout}
          >
            <LogOut size={18} aria-hidden="true" />
            <span className="sidebar-bottom-label">Log out</span>
          </button>
        </div>
      </aside>

      <nav className="mobile-bottom-nav" aria-label="Primary navigation">
        {primaryItems.map((item) => {
          const Icon = item.icon;
          const active = isNavigationItemActive(location.pathname, item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`mobile-tab ${active ? 'active' : ''}`}
              aria-current={active ? 'page' : undefined}
              aria-label={item.label}
            >
              <Icon size={20} aria-hidden="true" />
              <span>{item.shortLabel}</span>
            </Link>
          );
        })}
        <button
          ref={moreButtonRef}
          type="button"
          className={`mobile-tab ${moreIsActive || moreOpen ? 'active' : ''}`}
          aria-label="More navigation options"
          aria-haspopup="dialog"
          aria-controls="mobile-more-sheet"
          aria-expanded={moreOpen}
          onClick={() => {
            if (moreOpen) closeMore();
            else setMoreOpenPath(location.pathname);
          }}
        >
          <MoreHorizontal size={20} aria-hidden="true" />
          <span>More</span>
        </button>
      </nav>

      {moreOpen && (
        <MobileMoreMenu
          items={moreItems}
          plan={plan}
          onClose={closeMore}
          onNavigate={() => closeMore(false)}
          onLogout={handleLogout}
        />
      )}
    </>
  );
}
