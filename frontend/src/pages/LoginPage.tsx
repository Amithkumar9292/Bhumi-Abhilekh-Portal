import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, AlertCircle, Lock, User, ShieldCheck } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';
import { useTranslation } from '../i18n/useTranslation';

// Demo credentials are hidden from all users by default.
// Uncomment to show the 4 demo logins on the login page.
const DEMO_CREDS = [
// { role: 'ADMIN',    user: 'admin',           pass: 'Admin@1234' },
// { role: 'OFFICER',  user: 'officer_rajesh',  pass: 'Officer@1234' },
// { role: 'VERIFIER', user: 'verifier_priya',  pass: 'Verifier@1234' },
// { role: 'VIEWER',   user: 'viewer_anand',    pass: 'Viewer@1234' },
] as const;

export function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await authApi.login({ username, password });
      setAuth(response.user, response.access_token);
      navigate('/dashboard', { replace: true });
    } catch {
      setError(t('auth.loginFailed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-root">
      <div className="login-tricolor" />

      {/* Left branding panel */}
      <div className="login-brand">
        <div className="login-brand__emblem">
          <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
            <path d="M8 34L22 10L36 34" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M5 34H39" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M13 34V40" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M31 34V40" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            <circle cx="22" cy="10" r="3" fill="#FF9933"/>
          </svg>
        </div>
        <h1 className="login-brand__title">
          Intelligent Land Record<br/>
          <span className="login-brand__accent">Digitization System</span>
        </h1>
        <p className="login-brand__subtitle">
          National platform for digitizing, validating and managing land records across India's districts and tehsils.
        </p>
        <ul className="login-features">
          {['Khasra & Khatauni digitization','Multi-role verification workflow','Geospatial cadastral mapping','Complete audit trail','AI-assisted anomaly detection'].map(f=>(
            <li key={f} className="login-features__item">
              <span className="login-features__check">✓</span>{f}
            </li>
          ))}
        </ul>
        <div className="login-demo-notice">
          <AlertCircle size={13}/>
          <span><strong>Demo System</strong> — Synthetic data only. Not legally binding.</span>
        </div>
      </div>

      {/* Login card */}
      <div className="login-panel">
        <div className="login-card">
          <div className="login-card__header">
            <div className="login-card__ministry-logo">
              <ShieldCheck size={18} color="var(--brand-primary)"/>
            </div>
            <div>
              <div className="login-card__ministry">{t('auth.loginTitle')}</div>
              <div className="login-card__dept">Ministry of Rural Development, GoI</div>
            </div>
          </div>

          <h2 className="login-card__title">{t('auth.login')}</h2>
          <p className="login-card__hint">{t('auth.loginSubtitle')}</p>

          {error && (
            <div className="alert alert--error login-card__error">
              <AlertCircle size={14}/><span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate autoComplete="on">
            <div className="field">
              <label className="field__label" htmlFor="login-username">{t('auth.username')}</label>
              <div className="field__wrap">
                <User className="field__icon" size={14}/>
                <input id="login-username" type="text" className="field__input field__input--icon"
                  placeholder="e.g. officer_rajesh" value={username}
                  onChange={e=>setUsername(e.target.value)} required autoFocus autoComplete="username"/>
              </div>
            </div>

            <div className="field">
              <div className="field__label-row">
                <label className="field__label" htmlFor="login-password">{t('auth.password')}</label>
                <a href="#" className="field__link">Forgot password?</a>
              </div>
              <div className="field__wrap">
                <Lock className="field__icon" size={14}/>
                <input id="login-password" type={showPwd?'text':'password'} className="field__input field__input--icon field__input--trail"
                  placeholder="Enter your password" value={password}
                  onChange={e=>setPassword(e.target.value)} required autoComplete="current-password"/>
                <button type="button" className="field__trail" onClick={()=>setShowPwd(s=>!s)} aria-label={showPwd?'Hide password':'Show password'}>
                  {showPwd?<EyeOff size={14}/>:<Eye size={14}/>}
                </button>
              </div>
            </div>

            <button type="submit" className="btn btn--primary btn--lg login-submit"
              disabled={loading||!username||!password} id="login-submit-btn">
              {loading?<><span className="spinner spinner--sm"/>{t('auth.signingIn')}</>:t('auth.login')}
            </button>
          </form>

          {/* Demo credentials — hidden from all users. Uncomment to show.
          <div className="login-demo">
            <div className="login-demo__title">🔑 Demo Credentials — click to fill</div>
            <div className="login-demo__grid">
              {DEMO_CREDS.map(({role,user:u,pass})=>(
                <button key={role} type="button" className="login-demo__item"
                  onClick={()=>{setUsername(u);setPassword(pass);}}>
                  <span className={`role-badge role-badge--${role}`}>{role}</span>
                  <span className="login-demo__user">{u}</span>
                </button>
              ))}
            </div>
          </div>
          */}
        </div>
      </div>
    </div>
  );
}
