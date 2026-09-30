import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { useAuthStore } from './store/authStore';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60 * 1000, retry: 0, refetchOnWindowFocus: false } },
});

const p = (loader: () => Promise<{ [key: string]: React.ComponentType }>, key: string) =>
  lazy(() => loader().then(m => ({ default: m[key] })));

const DashboardPage         = p(() => import('./pages/DashboardPage.tsx'),        'DashboardPage');
const DocumentIntakePage    = p(() => import('./pages/DocumentIntakePage.tsx'),   'DocumentIntakePage');
const IntakeReviewPage      = p(() => import('./pages/IntakeReviewPage.tsx'),      'IntakeReviewPage');
const DocumentsPage         = p(() => import('./pages/DocumentsPage.tsx'),        'DocumentsPage');
const LandRecordsPage       = p(() => import('./pages/LandRecordsPage.tsx'),      'LandRecordsPage');
const LandRecordDetailPage  = p(() => import('./pages/LandRecordDetailPage.tsx'), 'LandRecordDetailPage');
const VerificationPage      = p(() => import('./pages/VerificationPage.tsx'),     'VerificationPage');
const MapPage               = p(() => import('./pages/MapPage.tsx'),              'MapPage');
const AnomaliesPage         = p(() => import('./pages/AnomaliesPage.tsx'),        'AnomaliesPage');
const ReportsPage           = p(() => import('./pages/ReportsPage.tsx'),          'ReportsPage');
const AuditTrailPage        = p(() => import('./pages/AuditTrailPage.tsx'),       'AuditTrailPage');
const UsersPage             = p(() => import('./pages/UsersPage.tsx'),            'UsersPage');
const IntegrationsPage      = p(() => import('./pages/IntegrationsPage.tsx'),     'IntegrationsPage');
const SettingsPage          = p(() => import('./pages/SettingsPage.tsx'),         'SettingsPage');
const PipelinePage          = p(() => import('./pages/PipelinePage.tsx'),         'PipelinePage');
const NotFoundPage          = p(() => import('./pages/NotFoundPage.tsx'),         'NotFoundPage');
const AdminPage             = p(() => import('./pages/AdminPage.tsx'),            'AdminPage');

function Loader() {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
      minHeight:'50vh', flexDirection:'column', gap:'var(--space-3)' }}>
      <div className="spinner spinner--lg spinner--dark" />
      <span style={{ color:'var(--text-secondary)', fontSize:'var(--text-sm)' }}>Loading…</span>
    </div>
  );
}

function AuthRedirect() {
  const { isAuthenticated } = useAuthStore();
  return <Navigate to={isAuthenticated ? '/dashboard' : '/login'} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<Loader />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route element={<ProtectedRoute />}>
              <Route path="/dashboard"           element={<DashboardPage />} />
              <Route path="/intake"              element={<DocumentIntakePage />} />
              <Route path="/intake/review/:jobId" element={<IntakeReviewPage />} />
              <Route path="/documents"           element={<DocumentsPage />} />
              <Route path="/land-records"        element={<LandRecordsPage />} />
              <Route path="/land-records/:id"    element={<LandRecordDetailPage />} />
              <Route path="/verification"        element={<VerificationPage />} />
              <Route path="/map"                 element={<MapPage />} />
              <Route path="/anomalies"           element={<AnomaliesPage />} />
              <Route path="/reports"             element={<ReportsPage />} />
              <Route path="/audit"               element={<AuditTrailPage />} />
              <Route path="/pipeline"            element={<PipelinePage />} />
              <Route path="/settings"            element={<SettingsPage />} />
              <Route path="/integrations"        element={<IntegrationsPage />} />
            </Route>

            <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
              <Route path="/users" element={<UsersPage />} />
              <Route path="/admin" element={<AdminPage />} />
            </Route>

            <Route path="/" element={<AuthRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
