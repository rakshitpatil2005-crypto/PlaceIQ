import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Activity, ArrowLeft, BriefcaseBusiness, ChevronLeft, ChevronRight, Users } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';
import api from '../api';
import { buildPlacementQuery, isPlacementStaffRole } from '../utils/placementDashboard';

const PAGE_SIZE = 25;
const SEMESTERS = Array.from({ length: 12 }, (_, index) => index + 1);

function titleFor(key) {
  return key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function componentEvidence(component) {
  if (!component || component.student_count === 0) return 'No evidence recorded';
  return `Measured for ${component.student_count} student${component.student_count === 1 ? '' : 's'}`;
}

function displayMetric(value, suffix = '') {
  return Number.isFinite(value) ? `${Math.round(value * 10) / 10}${suffix}` : '—';
}

function ErrorNotice({ error, onRetry }) {
  const forbidden = error?.status === 403;
  return (
    <section className="panel-card" role="alert">
      <h2 className="text-lg font-semibold text-slate-900">
        {forbidden ? 'Access forbidden' : 'Placement data could not be loaded'}
      </h2>
      <p className="mt-2 text-sm text-slate-600">
        {forbidden
          ? 'Your account is not authorized to view placement-cell analytics.'
          : 'The analytics service is unavailable. Your existing student dashboard is unaffected.'}
      </p>
      {!forbidden && onRetry && (
        <button type="button" className="action-button mt-4" onClick={onRetry}>Try again</button>
      )}
    </section>
  );
}

function MetricCard({ title, value, note }) {
  return (
    <article className="panel-card">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
      <p className="mt-2 text-xs text-slate-500">{note}</p>
    </article>
  );
}

function ReadinessTrend({ trend }) {
  const points = trend?.points || [];
  const chartPoints = points.filter((point) => Number.isFinite(point.average_readiness));
  return (
    <section className="panel-card">
      <div className="flex items-center gap-2">
        <Activity size={18} aria-hidden="true" />
        <h2 className="text-lg font-semibold text-slate-900">Recorded readiness trend</h2>
      </div>
      {trend?.status !== 'available' || chartPoints.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600">
          {trend?.status === 'insufficient_history'
            ? 'History is sparse; there are not enough recorded snapshots to show a trend.'
            : 'No recorded readiness history is available for this cohort.'}
        </p>
      ) : (
        <div className="mt-4 h-64 w-full" role="img" aria-label="Recorded readiness trend chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartPoints} margin={{ top: 12, right: 12, bottom: 4, left: -12 }}>
              <CartesianGrid stroke="#e7ebf4" strokeDasharray="4 4" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(value, _name, item) => [
                  `${displayMetric(Number(value), '%')} · ${item.payload.student_count} students`,
                  'Average readiness',
                ]}
                contentStyle={{ borderRadius: 12, borderColor: '#e1e7f1', boxShadow: '0 8px 24px rgba(38,52,83,.12)' }}
              />
              <Legend />
              <Line
                name="Average readiness"
                type="monotone"
                dataKey="average_readiness"
                stroke="#4f46e5"
                strokeWidth={3}
                dot={{ r: 4, fill: '#4f46e5', strokeWidth: 2, stroke: '#fff' }}
                activeDot={{ r: 6 }}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

function ComponentEvidenceChart({ components }) {
  const colors = ['#4f46e5', '#0ea5e9', '#7c3aed', '#0f766e'];
  const data = Object.entries(components || {})
    .filter(([, component]) => Number.isFinite(component?.average))
    .map(([name, component]) => ({
      name: titleFor(name),
      average: component.average,
      student_count: component.student_count,
    }));

  return (
    <section className="panel-card">
      <h2 className="text-lg font-semibold text-slate-900">Component evidence</h2>
      <p className="mt-1 text-sm text-slate-500">Missing evidence is shown separately from measured scores.</p>
      {data.length ? (
        <>
          <div className="mt-4 h-64 w-full" role="img" aria-label="Average readiness by component chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="#e7ebf4" strokeDasharray="4 4" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={92} tick={{ fill: '#475569', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(value, _name, item) => [
                    `${displayMetric(Number(value), '%')} · ${item.payload.student_count} students`,
                    'Measured average',
                  ]}
                  contentStyle={{ borderRadius: 12, borderColor: '#e1e7f1', boxShadow: '0 8px 24px rgba(38,52,83,.12)' }}
                />
                <Legend />
                <Bar name="Measured average" dataKey="average" radius={[0, 7, 7, 0]} maxBarSize={28}>
                  {data.map((item, index) => <Cell key={item.name} fill={colors[index % colors.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-500">Only components with recorded measurements are plotted.</p>
        </>
      ) : (
        <p className="mt-4 text-sm text-slate-600">No component score evidence is available to chart.</p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(components || {}).map(([name, component]) => (
          <div key={name} className="rounded-xl border border-slate-100 bg-slate-50/80 p-4">
            <p className="text-sm font-medium capitalize text-slate-600">{titleFor(name)}</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">
              {displayMetric(component.average, component.average == null ? '' : '%')}
            </p>
            <p className="mt-1 text-xs text-slate-500">{componentEvidence(component)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PlacementDashboardView({
  access = 'allowed',
  loading = false,
  error = null,
  summary = null,
  directory = null,
  detail = null,
  filters = { branch: '', semester: '', target_role: '' },
  onChangeFilters = () => {},
  onApplyFilters = () => {},
  page = 1,
  sortBy = 'name',
  sortOrder = 'asc',
  onPageChange = () => {},
  onSortChange = () => {},
  onRetry = () => {},
  studentId = null,
}) {
  if (access === 'loading') {
    return <section className="panel-card" role="status">Checking placement dashboard access…</section>;
  }
  if (access === 'forbidden') return <ErrorNotice error={{ status: 403 }} />;
  if (loading) {
    return <section className="panel-card" role="status">Loading placement-cell analytics…</section>;
  }
  if (error) return <ErrorNotice error={error} onRetry={onRetry} />;

  if (studentId) {
    if (!detail) return <section className="panel-card" role="status">Loading student detail…</section>;
    const student = detail.student || {};
    const readiness = detail.readiness || {};
    const roadmap = detail.roadmap || {};
    const interview = detail.interview || {};
    const gap = detail.skill_gap || {};
    const history = detail.recorded_readiness_history || {};
    return (
      <div className="space-y-6">
        <Link to="/placement" className="inline-flex items-center gap-2 text-sm font-medium text-indigo-700">
          <ArrowLeft size={16} aria-hidden="true" /> Back to placement dashboard
        </Link>
        <header>
          <p className="text-sm font-medium text-indigo-700">Authorized student drill-down</p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">{student.name || 'Student record'}</h1>
          <p className="mt-2 text-sm text-slate-600">
            {[student.branch, student.semester ? `Semester ${student.semester}` : null, student.target_role]
              .filter(Boolean).join(' · ') || 'Profile details unavailable'}
          </p>
        </header>
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard title="Readiness" value={displayMetric(readiness.score, '%')} note={`${readiness.evidence_coverage?.available_components ?? 0} of ${readiness.evidence_coverage?.total_components ?? 4} components measured`} />
          <MetricCard title="Roadmap progress" value={displayMetric(roadmap.progress_pct, '%')} note={`${roadmap.completed_tasks ?? 0} of ${roadmap.total_tasks ?? 0} recorded tasks complete`} />
          <MetricCard title="Interview score" value={displayMetric(interview.score)} note={interview.score == null ? 'No completed interview evidence' : 'Latest completed interview'} />
          <MetricCard title="Skill match" value={displayMetric(gap.match_pct, '%')} note={gap.match_pct == null ? 'No matching skill-gap report' : 'Latest matching skill-gap report'} />
        </section>
        <section className="panel-card">
          <h2 className="text-lg font-semibold text-slate-900">Readiness evidence</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {Object.entries(readiness.components || {}).map(([name, value]) => (
              <div key={name} className="rounded-lg bg-slate-50 p-3">
                <p className="text-sm capitalize text-slate-500">{name.replaceAll('_', ' ')}</p>
                <p className="mt-1 font-semibold text-slate-900">{displayMetric(value, value == null ? '' : '%')}</p>
                {value == null && <p className="text-xs text-slate-500">No evidence recorded</p>}
              </div>
            ))}
          </div>
        </section>
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="panel-card">
            <h2 className="text-lg font-semibold text-slate-900">Missing skills</h2>
            {gap.missing_skills?.length ? (
              <ul className="mt-3 flex flex-wrap gap-2">
                {gap.missing_skills.map((skill) => <li key={skill} className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-900">{skill}</li>)}
              </ul>
            ) : <p className="mt-3 text-sm text-slate-600">No missing-skill evidence recorded.</p>}
            <h3 className="mt-5 font-medium text-slate-800">Interview focus</h3>
            {interview.weak_skills?.length
              ? <p className="mt-2 text-sm text-slate-600">{interview.weak_skills.join(', ')}</p>
              : <p className="mt-2 text-sm text-slate-600">No interview focus evidence recorded.</p>}
          </section>
          <ReadinessTrend trend={history} />
        </div>
      </div>
    );
  }

  const cohort = summary?.cohort || {};
  const readiness = summary?.readiness || {};
  const components = summary?.components || {};
  const roadmap = summary?.roadmap || {};
  const interviews = summary?.interviews || {};
  const students = directory?.students || [];
  const pageCount = Math.max(1, Math.ceil((directory?.total_students || 0) / (directory?.page_size || 1)));
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-medium text-indigo-700"><BriefcaseBusiness size={16} /> Placement Cell</p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">Cohort readiness</h1>
          <p className="mt-2 text-sm text-slate-600">Aggregate placement evidence from existing student records.</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-2 text-sm text-slate-700">
          <Users size={16} aria-hidden="true" /> {cohort.student_count ?? 0} students
        </div>
      </header>

      <form
        className="panel-card grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => { event.preventDefault(); onApplyFilters(); }}
        aria-label="Placement cohort filters"
      >
        <label className="text-sm text-slate-600">
          Branch
          <input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={filters.branch} onChange={(event) => onChangeFilters({ ...filters, branch: event.target.value })} placeholder="All branches" />
        </label>
        <label className="text-sm text-slate-600">
          Semester
          <select className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={filters.semester} onChange={(event) => onChangeFilters({ ...filters, semester: event.target.value })}>
            <option value="">All semesters</option>
            {SEMESTERS.map((semester) => <option key={semester} value={semester}>{semester}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Target role
          <input className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" value={filters.target_role} onChange={(event) => onChangeFilters({ ...filters, target_role: event.target.value })} placeholder="All target roles" />
        </label>
        <button type="submit" className="action-button self-end">Apply filters</button>
      </form>

      {cohort.status === 'empty' ? (
        <section className="panel-card" role="status">
          <h2 className="text-lg font-semibold text-slate-900">No students match these filters</h2>
          <p className="mt-2 text-sm text-slate-600">Change or clear the filters to view another cohort. No metrics are inferred for an empty cohort.</p>
        </section>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard title="Average readiness" value={displayMetric(readiness.average, '%')} note={readiness.student_count ? `Measured across ${readiness.student_count} students` : 'No readiness evidence recorded'} />
            <MetricCard title="Evidence coverage" value={readiness.student_count ? `${readiness.student_count} / ${cohort.student_count || 0}` : '—'} note="Students with at least one readiness measure" />
            <MetricCard title="Roadmap completion" value={displayMetric(roadmap.average_progress_pct, '%')} note={roadmap.total_tasks ? `${roadmap.completed_tasks} of ${roadmap.total_tasks} recorded tasks complete` : 'No roadmap task evidence recorded'} />
            <MetricCard title="Interview performance" value={displayMetric(interviews.average_score)} note={interviews.student_count ? `Latest completed interview for ${interviews.student_count} students` : 'No completed interview evidence'} />
          </section>

          <ComponentEvidenceChart components={components} />

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="panel-card">
              <h2 className="text-lg font-semibold text-slate-900">Common missing skills</h2>
              {summary?.common_missing_skills?.skills?.length ? (
                <>
                  <p className="mt-1 text-sm text-slate-500">Across {summary.common_missing_skills.student_count} students with skill-gap evidence</p>
                  <ul className="mt-4 space-y-3">
                    {summary.common_missing_skills.skills.map(({ skill, student_count }) => (
                      <li key={skill} className="flex items-center justify-between gap-3 text-sm">
                        <span className="font-medium text-slate-800">{skill}</span>
                        <span className="text-slate-500">{student_count} student{student_count === 1 ? '' : 's'}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : <p className="mt-3 text-sm text-slate-600">No missing-skill evidence is available for this cohort.</p>}
            </section>
            <ReadinessTrend trend={summary?.readiness_trend} />
          </div>

          <section className="panel-card">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Student directory</h2>
                <p className="mt-1 text-sm text-slate-500">{directory?.total_students ?? 0} matching student records</p>
              </div>
              <label className="text-sm text-slate-600">
                Sort
                <select className="ml-2 rounded-lg border border-slate-300 px-2 py-2" value={`${sortBy}:${sortOrder}`} onChange={(event) => onSortChange(event.target.value)}>
                  {['name', 'branch', 'semester', 'readiness'].flatMap((field) => [
                    <option key={`${field}:asc`} value={`${field}:asc`}>{titleFor(field)} ascending</option>,
                    <option key={`${field}:desc`} value={`${field}:desc`}>{titleFor(field)} descending</option>,
                  ])}
                </select>
              </label>
            </div>
            {students.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                    <tr><th className="px-3 py-3">Student</th><th className="px-3 py-3">Branch / semester</th><th className="px-3 py-3">Target role</th><th className="px-3 py-3">Readiness</th><th className="px-3 py-3">Coverage</th><th className="px-3 py-3">Roadmap</th><th className="px-3 py-3">Interview</th><th className="px-3 py-3"><span className="sr-only">Details</span></th></tr>
                  </thead>
                  <tbody>
                    {students.map((student) => (
                      <tr key={student.user_id} className="border-b border-slate-100">
                        <td className="px-3 py-3 font-medium text-slate-900">{student.name || 'Unnamed student'}</td>
                        <td className="px-3 py-3 text-slate-600">{[student.branch, student.semester ? `Sem ${student.semester}` : null].filter(Boolean).join(' · ') || '—'}</td>
                        <td className="px-3 py-3 text-slate-600">{student.target_role || '—'}</td>
                        <td className="px-3 py-3 text-slate-600">{displayMetric(student.readiness_score, student.readiness_score == null ? '' : '%')}</td>
                        <td className="px-3 py-3 text-slate-600">{student.evidence_coverage?.available_components ?? 0} / {student.evidence_coverage?.total_components ?? 4}</td>
                        <td className="px-3 py-3 text-slate-600">{displayMetric(student.roadmap_progress_pct, student.roadmap_progress_pct == null ? '' : '%')}</td>
                        <td className="px-3 py-3 text-slate-600">{displayMetric(student.interview_score)}</td>
                        <td className="px-3 py-3"><Link className="font-medium text-indigo-700 hover:underline" to={`/placement/students/${student.user_id}`}>View details</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="mt-4 text-sm text-slate-600">No student records are available on this page.</p>}
            <div className="mt-4 flex items-center justify-between">
              <button type="button" className="action-button" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
                <ChevronLeft size={16} aria-hidden="true" /> Previous
              </button>
              <span className="text-sm text-slate-600">Page {page} of {pageCount}</span>
              <button type="button" className="action-button" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount}>
                Next <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default function PlacementDashboard() {
  const { studentId } = useParams();
  const [access, setAccess] = useState('loading');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [directory, setDirectory] = useState(null);
  const [detailRecord, setDetailRecord] = useState(null);
  const [filters, setFilters] = useState({ branch: '', semester: '', target_role: '' });
  const [appliedFilters, setAppliedFilters] = useState({ branch: '', semester: '', target_role: '' });
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');
  const [reload, setReload] = useState(0);
  const [authAttempt, setAuthAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    api.get('/auth/me')
      .then(({ data }) => {
        if (active) setAccess(isPlacementStaffRole(data.role) ? 'allowed' : 'forbidden');
      })
      .catch((requestError) => {
        if (active) {
          setAccess(requestError.response?.status === 403 ? 'forbidden' : 'error');
          setError({ status: requestError.response?.status });
        }
      });
    return () => { active = false; };
  }, [authAttempt]);

  useEffect(() => {
    if (access !== 'allowed') return undefined;
    let active = true;
    if (studentId) {
      api.get(`/placement/students/${encodeURIComponent(studentId)}`)
        .then(({ data }) => {
          if (active) {
            setError(null);
            setDetailRecord({ studentId, data });
          }
        })
        .catch((requestError) => { if (active) setError({ status: requestError.response?.status }); })
        .finally(() => { if (active) setLoading(false); });
    } else {
      const params = buildPlacementQuery(appliedFilters, page, PAGE_SIZE, sortBy, sortOrder);
      const filterParams = Object.fromEntries(
        ['branch', 'semester', 'target_role']
          .filter((key) => params[key] !== undefined)
          .map((key) => [key, params[key]]),
      );
      Promise.all([
        api.get('/placement/dashboard', { params: filterParams }),
        api.get('/placement/students', { params }),
      ])
        .then(([summaryResponse, directoryResponse]) => {
          if (active) {
            setError(null);
            setSummary(summaryResponse.data);
            setDirectory(directoryResponse.data);
          }
        })
        .catch((requestError) => { if (active) setError({ status: requestError.response?.status }); })
        .finally(() => { if (active) setLoading(false); });
    }
    return () => { active = false; };
  }, [access, studentId, appliedFilters, page, sortBy, sortOrder, reload]);

  const applyFilters = () => {
    setLoading(true);
    setError(null);
    setPage(1);
    setAppliedFilters(filters);
  };
  const changeSort = (value) => {
    const [field, order] = value.split(':');
    setLoading(true);
    setError(null);
    setSortBy(field);
    setSortOrder(order);
    setPage(1);
  };
  const changePage = (nextPage) => {
    setLoading(true);
    setError(null);
    setPage(nextPage);
  };
  const retry = () => {
    setLoading(true);
    setError(null);
    setReload((value) => value + 1);
  };

  if (access === 'error') {
    return <ErrorNotice error={error || { status: 500 }} onRetry={() => { setAccess('loading'); setError(null); setAuthAttempt((value) => value + 1); }} />;
  }
  return (
    <PlacementDashboardView
      access={access}
      loading={loading || (studentId ? detailRecord?.studentId !== studentId : !summary || !directory)}
      error={error}
      summary={summary}
      directory={directory}
      detail={studentId && detailRecord?.studentId === studentId ? detailRecord.data : null}
      filters={filters}
      onChangeFilters={setFilters}
      onApplyFilters={applyFilters}
      page={page}
      sortBy={sortBy}
      sortOrder={sortOrder}
      onPageChange={changePage}
      onSortChange={changeSort}
      onRetry={retry}
      studentId={studentId}
    />
  );
}
