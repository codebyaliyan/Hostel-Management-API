import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowUpFromLine, BedDouble, Building2,
  CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleUserRound,
  ClipboardCheck, Clock3, DoorOpen, Globe2, GraduationCap, LayoutDashboard,
  LoaderCircle, LogOut, MapPin, Menu, Plus, RefreshCw, Search, ShieldCheck,
  Sparkles, Trash2, Users, Wifi, Wrench, X, UserRound, Eye, Pencil, KeyRound,
  CircleCheck, CircleX, House, Network, UserCog, Filter, Phone, Mail, Hash,
} from 'lucide-react'

const TOKEN_KEY = 'staywise_token'
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const PAGE_SIZE = 50

const WORKSPACE_NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'students', label: 'Students', icon: GraduationCap },
  { id: 'rooms', label: 'Rooms & beds', icon: BedDouble },
  { id: 'allocations', label: 'Allocations', icon: ClipboardCheck },
  { id: 'services', label: 'Services', icon: Wrench },
  { id: 'visitors', label: 'Visitors', icon: UserRound },
  { id: 'leaves', label: 'Leave requests', icon: CalendarDays },
  { id: 'attendance', label: 'Attendance', icon: Clock3 },
]
const PAGE_LABELS = Object.fromEntries(WORKSPACE_NAV.map(item => [item.id, item.label]))
const WORKSPACE_PAGES = WORKSPACE_NAV.map(item => item.id).filter(id => id !== 'dashboard')

const FORM_CONFIG = {
  students: {
    title: 'student', endpoint: '/students', fields: [
      { key: 'first_name', label: 'First name', required: true },
      { key: 'last_name', label: 'Last name', required: true },
      { key: 'father_name', label: 'Father name' },
      { key: 'mother_name', label: 'Mother name' },
      { key: 'dob', label: 'Date of birth', type: 'date', required: true },
      { key: 'contact', label: 'Contact number', required: true },
      { key: 'email', label: 'Email address', type: 'email' },
      { key: 'gender', label: 'Gender', type: 'select', required: true, options: ['Male', 'Female', 'Other'] },
      { key: 'address', label: 'Address', type: 'textarea' },
      { key: 'vehicle_number', label: 'Vehicle number' },
      { key: 'college_workplace', label: 'College / workplace' },
    ],
  },
  rooms: {
    title: 'room', endpoint: '/rooms', fields: [
      { key: 'room_number', label: 'Room number', required: true, placeholder: 'e.g. 101' },
      { key: 'floor', label: 'Floor', type: 'number', required: true, min: 0 },
      { key: 'capacity', label: 'Bed capacity', type: 'number', required: true, min: 1, max: 20 },
      { key: 'gender', label: 'Room gender', type: 'select', required: true, options: ['Male', 'Female', 'Other'] },
    ],
  },
  services: {
    title: 'service', endpoint: '/services', fields: [
      { key: 'name', label: 'Service name', required: true, placeholder: 'e.g. Laundry' },
      { key: 'description', label: 'Description', type: 'textarea' },
    ],
  },
  visitors: {
    title: 'visitor entry', endpoint: '/visitors', fields: [
      { key: 'student_id', label: 'Resident student', type: 'student', required: true },
      { key: 'visitor_name', label: 'Visitor name', required: true },
      { key: 'contact', label: 'Contact number', required: true },
      { key: 'reason', label: 'Reason for visit', required: true },
      { key: 'address', label: 'Visitor address', type: 'textarea' },
    ],
  },
  leaves: {
    title: 'leave request', endpoint: '/leaves', fields: [
      { key: 'student_id', label: 'Resident student', type: 'student', required: true },
      { key: 'reason', label: 'Reason', type: 'textarea', required: true },
      { key: 'application_date', label: 'Leave starts', type: 'date', required: true },
      { key: 'return_date', label: 'Expected return', type: 'date', required: true },
    ],
  },
}

const TABLE_CONFIG = {
  students: { title: 'Students', description: 'Resident records assigned to this branch.', columns: [['id', 'ID'], ['first_name', 'First name'], ['last_name', 'Last name'], ['gender', 'Gender'], ['contact', 'Contact']] },
  rooms: { title: 'Rooms & beds', description: 'Rooms and their generated bed inventory.', columns: [['id', 'ID'], ['room_number', 'Room'], ['floor', 'Floor'], ['gender', 'Gender'], ['capacity', 'Capacity'], ['total_beds', 'Beds'], ['available_beds', 'Available'], ['status', 'Status']] },
  allocations: { title: 'Allocations', description: 'Current and historical resident bed allocations.', columns: [['id', 'ID'], ['student_name', 'Student'], ['room_number', 'Room'], ['bed_name', 'Bed'], ['allocated_date', 'Allocated'], ['checkout_date', 'Checkout'], ['status', 'Status']] },
  services: { title: 'Services', description: 'Facilities and services available at this branch.', columns: [['id', 'ID'], ['name', 'Service'], ['description', 'Description']] },
  visitors: { title: 'Visitors', description: 'Visitor check-in records for residents.', columns: [['id', 'ID'], ['student_name', 'Resident'], ['visitor_name', 'Visitor'], ['contact', 'Contact'], ['reason', 'Reason'], ['check_in', 'Check-in'], ['check_out', 'Check-out'], ['status', 'Status']] },
  leaves: { title: 'Leave requests', description: 'Review leave applications submitted for residents.', columns: [['id', 'ID'], ['student_name', 'Student'], ['reason', 'Reason'], ['application_date', 'From'], ['return_date', 'Return'], ['status', 'Status']] },
  attendance: { title: 'Attendance', description: 'Record resident exits and returns.', columns: [['id', 'ID'], ['student_name', 'Student'], ['purpose', 'Purpose'], ['out_time', 'Out time'], ['in_time', 'In time'], ['status', 'Status']] },
}

async function api(path, options = {}) {
  const { skipAuth = false, ...fetchOptions } = options
  const headers = { Accept: 'application/json', ...(fetchOptions.body ? { 'Content-Type': 'application/json' } : {}), ...fetchOptions.headers }
  const token = localStorage.getItem(TOKEN_KEY)
  if (!skipAuth && token) headers.Authorization = `Bearer ${token}`
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers })
  } catch {
    throw new Error('Could not reach the API. Start Flask on port 5000 and check the frontend API proxy.')
  }
  let result = {}
  try { result = await response.json() } catch { /* non-JSON API response */ }
  if (!response.ok || result.success === false) {
    throw new Error(result.error || result.message || `Request failed (${response.status})`)
  }
  return result
}

const blankFor = fields => Object.fromEntries(fields.map(field => [field.key, '']))
const dateText = value => value == null || value === '' ? '—' : String(value).replace('T', ' ').replace(/\.\d+$/, '')
const numberText = value => Number(value || 0).toLocaleString()
const fullName = row => [row?.first_name, row?.last_name].filter(Boolean).join(' ')
const initials = user => (user?.full_name || user?.username || 'HM').split(/[\s._-]+/).filter(Boolean).slice(0, 2).map(part => part[0]?.toUpperCase()).join('')

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(Boolean(localStorage.getItem(TOKEN_KEY)))
  const [username, setUsername] = useState('superadmin')
  const [password, setPassword] = useState('admin123')
  const [loginBusy, setLoginBusy] = useState(false)
  const [page, setPage] = useState('network')
  const [activeBranchId, setActiveBranchId] = useState('')
  const [branches, setBranches] = useState([])
  const [cities, setCities] = useState([])
  const [network, setNetwork] = useState(null)
  const [locationsLoaded, setLocationsLoaded] = useState(false)
  const [records, setRecords] = useState({})
  const [dashboard, setDashboard] = useState(null)
  const [pagination, setPagination] = useState({})
  const [pageNumbers, setPageNumbers] = useState({})
  const [lookups, setLookups] = useState({ students: [], rooms: [], beds: [] })
  const [roomBedModal, setRoomBedModal] = useState(null)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({})
  const [search, setSearch] = useState('')
  const [cityFilter, setCityFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const isSuperAdmin = user?.role === 'super_admin'
  const branch = branches.find(item => String(item.id) === String(activeBranchId))
  const isWorkspacePage = page === 'dashboard' || WORKSPACE_PAGES.includes(page)

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken('')
    setUser(null)
    setActiveBranchId('')
    setBranches([])
    setCities([])
    setNetwork(null)
    setRecords({})
    setDashboard(null)
    setPage('network')
    setModal(null)
    setRoomBedModal(null)
    setError('')
    setNotice('')
  }, [])

  const refreshLocations = useCallback(async () => {
    const [cityResult, branchResult, networkResult] = await Promise.all([
      api('/cities'), api('/branches'), api('/network/overview'),
    ])
    setCities(Array.isArray(cityResult.data) ? cityResult.data : [])
    setBranches(Array.isArray(branchResult.data) ? branchResult.data : [])
    setNetwork(networkResult.data || null)
    setLocationsLoaded(true)
  }, [])

  const loadNetwork = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api(`/network/overview${cityFilter ? `?city_id=${encodeURIComponent(cityFilter)}` : ''}`)
      setNetwork(result.data || null)
    } catch (e) {
      setError(e.message)
      if (/token|login required|account not found/i.test(e.message)) signOut()
    } finally { setLoading(false) }
  }, [cityFilter, signOut])

  const loadLocations = useCallback(async () => {
    setLoading(true)
    setError('')
    try { await refreshLocations() }
    catch (e) {
      setError(e.message)
      if (/token|login required|account not found/i.test(e.message)) signOut()
    } finally { setLoading(false) }
  }, [refreshLocations, signOut])

  const scopedPath = useCallback((path) => `/branches/${encodeURIComponent(activeBranchId)}${path}`, [activeBranchId])

  const loadWorkspace = useCallback(async (target = page, pageNumber = 1) => {
    if (!activeBranchId) return
    setLoading(true)
    setError('')
    const listPath = path => `${scopedPath(path)}?page=${pageNumber}&limit=${PAGE_SIZE}`
    try {
      if (target === 'dashboard') {
        const [stats, students, rooms] = await Promise.all([
          api(scopedPath('/dashboard')),
          api(`${scopedPath('/students')}?limit=5`),
          api(`${scopedPath('/rooms')}?limit=5`),
        ])
        setDashboard(stats.data || null)
        setRecords(current => ({ ...current, students: students.data || [], rooms: rooms.data || [] }))
      } else {
        const config = TABLE_CONFIG[target]
        if (!config) return
        const path = target === 'services' ? scopedPath('/services') : listPath(`/${target}`)
        const result = await api(path)
        setRecords(current => ({ ...current, [target]: Array.isArray(result.data) ? result.data : [] }))
        if (result.meta) setPagination(current => ({ ...current, [target]: result.meta }))
        setPageNumbers(current => ({ ...current, [target]: pageNumber }))
      }
    } catch (e) {
      setError(e.message)
      if (/token|login required|account not found/i.test(e.message)) signOut()
    } finally { setLoading(false) }
  }, [activeBranchId, page, scopedPath, signOut])

  useEffect(() => {
    let cancelled = false
    async function restoreSession() {
      const saved = localStorage.getItem(TOKEN_KEY)
      if (!saved) { setBooting(false); return }
      try {
        const result = await api('/auth/me')
        if (cancelled) return
        const currentUser = result.data
        setToken(saved)
        setUser(currentUser)
        setActiveBranchId(currentUser?.role === 'branch_admin' && currentUser?.branch_id ? String(currentUser.branch_id) : '')
        setPage(currentUser?.role === 'super_admin' ? 'network' : 'dashboard')
      } catch {
        localStorage.removeItem(TOKEN_KEY)
        if (!cancelled) { setToken(''); setUser(null) }
      } finally { if (!cancelled) setBooting(false) }
    }
    restoreSession()
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!token || !user) return
    refreshLocations().catch(e => setError(e.message))
  }, [token, user?.id, refreshLocations])

  useEffect(() => {
    if (!token || !user) return
    if (page === 'network') loadNetwork()
    else if (page === 'locations') loadLocations()
    else if (isWorkspacePage && activeBranchId) loadWorkspace(page, 1)
  }, [token, user?.id, page, activeBranchId, isWorkspacePage, loadNetwork, loadLocations, loadWorkspace])

  useEffect(() => { setSearch(''); setSidebarOpen(false); setError(''); setNotice('') }, [page, activeBranchId])

  async function handleLogin(event) {
    event.preventDefault()
    setLoginBusy(true)
    setError('')
    try {
      const result = await api('/auth/login', { method: 'POST', skipAuth: true, body: JSON.stringify({ username: username.trim(), password }) })
      const newToken = result.data?.token
      if (!newToken) throw new Error('The API did not return an authentication token.')
      localStorage.setItem(TOKEN_KEY, newToken)
      setToken(newToken)
      setUser(result.data.user)
      setActiveBranchId(result.data.user?.role === 'branch_admin' && result.data.user?.branch_id ? String(result.data.user.branch_id) : '')
      setPage(result.data.user?.role === 'super_admin' ? 'network' : 'dashboard')
      setPassword('')
      setNotice(`Welcome${result.data.user?.full_name ? `, ${result.data.user.full_name}` : ''}.`)
    } catch (e) { setError(e.message) }
    finally { setLoginBusy(false); setBooting(false) }
  }

  async function reloadCurrent() {
    if (page === 'network') return loadNetwork()
    if (page === 'locations') return loadLocations()
    if (isWorkspacePage) return loadWorkspace(page, pageNumbers[page] || 1)
  }

  function goTo(target) {
    setPage(target)
    setModal(null)
    setRoomBedModal(null)
    setSidebarOpen(false)
  }

  function openBranchEdit(item) {
    setForm({ city_id: String(item.city_id), name: item.name || '', code: item.code || '', address: item.address || '', contact: item.contact || '' })
    setModal({ kind: 'branch', mode: 'edit', id: item.id, isActive: Boolean(item.is_active), branchName: item.name })
  }

  async function openBranchAdmins(item) {
    setModal({ kind: 'admins-list', branchId: item.id, branchName: item.name, admins: [], loading: true, error: '' })
    try {
      const result = await api(`/branches/${item.id}/admins`)
      setModal(current => current?.kind === 'admins-list' && current.branchId === item.id ? { ...current, admins: result.data || [], loading: false } : current)
    } catch (e) {
      setModal(current => current?.kind === 'admins-list' && current.branchId === item.id ? { ...current, loading: false, error: e.message } : current)
    }
  }

  async function openRecordCreate(entity) {
    const config = FORM_CONFIG[entity]
    if (!config) return
    setError('')
    setForm(blankFor(config.fields))
    setModal({ kind: 'record', entity, mode: 'create' })
    if (['visitors', 'leaves'].includes(entity)) await loadLookups(['students'])
  }

  async function openStudentEdit(student) {
    setSaving(true)
    setError('')
    try {
      const result = await api(scopedPath(`/students/${student.id}`))
      const config = FORM_CONFIG.students
      setForm(Object.fromEntries(config.fields.map(field => [field.key, result.data?.[field.key] ?? ''])))
      setModal({ kind: 'record', entity: 'students', mode: 'edit', id: student.id })
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function loadLookups(required = ['students', 'rooms', 'beds']) {
    if (!activeBranchId) return
    try {
      const wanted = {}
      if (required.includes('students')) wanted.students = api(`${scopedPath('/students')}?limit=200`)
      if (required.includes('rooms')) wanted.rooms = api(`${scopedPath('/rooms')}?limit=200`)
      if (required.includes('beds')) wanted.beds = api(`${scopedPath('/beds/available')}?limit=200`)
      const keys = Object.keys(wanted)
      const values = await Promise.all(Object.values(wanted))
      setLookups(old => ({ ...old, ...Object.fromEntries(keys.map((key, i) => [key, values[i].data || []])) }))
    } catch (e) { setError(e.message) }
  }

  async function openAllocationForm() {
    setForm({ student_id: '', room_id: '', bed_id: '' })
    setModal({ kind: 'allocation' })
    await loadLookups(['students', 'rooms', 'beds'])
  }

  async function openAttendanceForm(mode) {
    setForm({ student_id: '', purpose: '', remarks: '' })
    setModal({ kind: 'attendance', mode })
    await loadLookups(['students'])
  }

  async function openRoomBeds(room) {
    setRoomBedModal({ room, loading: true, beds: [], error: '' })
    try {
      const result = await api(scopedPath(`/rooms/${room.id}/beds`))
      setRoomBedModal({ room, loading: false, beds: result.data || [], error: '' })
    } catch (e) { setRoomBedModal({ room, loading: false, beds: [], error: e.message }) }
  }

  function payloadFrom(fields, current) {
    const payload = {}
    for (const field of fields) {
      const value = current[field.key]
      if (field.type === 'number' || field.type === 'student') payload[field.key] = value === '' || value == null ? '' : Number(value)
      else payload[field.key] = value == null ? '' : value
    }
    return payload
  }

  async function submitModal(event) {
    event.preventDefault()
    if (!modal) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      let result
      if (modal.kind === 'record') {
        const cfg = FORM_CONFIG[modal.entity]
        const method = modal.mode === 'edit' ? 'PUT' : 'POST'
        const endpoint = `${scopedPath(cfg.endpoint)}${modal.mode === 'edit' ? `/${modal.id}` : ''}`
        result = await api(endpoint, { method, body: JSON.stringify(payloadFrom(cfg.fields, form)) })
      } else if (modal.kind === 'allocation') {
        if (!form.student_id || !form.room_id || !form.bed_id) throw new Error('Choose a student, room, and available bed.')
        result = await api(scopedPath('/allocations'), { method: 'POST', body: JSON.stringify({ student_id: Number(form.student_id), room_id: Number(form.room_id), bed_id: Number(form.bed_id) }) })
      } else if (modal.kind === 'attendance') {
        const isOut = modal.mode === 'out'
        if (!form.student_id) throw new Error('Choose a student first.')
        if (isOut && !form.purpose.trim()) throw new Error('Purpose is required when marking a student OUT.')
        const body = { student_id: Number(form.student_id) }
        if (isOut) { body.purpose = form.purpose.trim(); body.remarks = form.remarks.trim() }
        result = await api(scopedPath(`/attendance/${isOut ? 'out' : 'in'}`), { method: 'POST', body: JSON.stringify(body) })
      } else if (modal.kind === 'city') {
        result = await api('/cities', { method: 'POST', body: JSON.stringify(form) })
      } else if (modal.kind === 'branch') {
        const payload = { ...form, city_id: Number(form.city_id) }
        if (modal.mode === 'edit') {
          payload.is_active = modal.isActive
          result = await api(`/branches/${modal.id}`, { method: 'PUT', body: JSON.stringify(payload) })
        } else {
          result = await api('/branches', { method: 'POST', body: JSON.stringify(payload) })
        }
      } else if (modal.kind === 'admin') {
        result = await api(`/branches/${modal.branchId}/admins`, { method: 'POST', body: JSON.stringify(form) })
      } else if (modal.kind === 'admin-edit') {
        const body = { username: form.username.trim(), full_name: form.full_name || '', is_active: modal.isActive }
        if (form.password) body.password = form.password   // blank = keep the current password
        result = await api(`/branches/${modal.branchId}/admins/${modal.adminId}`, { method: 'PUT', body: JSON.stringify(body) })
      }
      let successMessage = result?.message || 'Changes saved successfully.'
      const defaultAdmin = result?.data?.default_admin
      if (modal.kind === 'branch' && defaultAdmin) successMessage += `. Default admin login: ${defaultAdmin.username} / ${defaultAdmin.password}`
      setModal(null)
      setNotice(successMessage)
      if (modal.kind === 'city' || modal.kind === 'branch' || modal.kind === 'admin') await refreshLocations()
      else if (modal.kind === 'admin-edit') await openBranchAdmins({ id: modal.branchId, name: modal.branchName })
      else if (modal.kind === 'record' || modal.kind === 'allocation' || modal.kind === 'attendance') {
        await loadWorkspace(page, pageNumbers[page] || 1)
        if (page !== 'dashboard') await loadWorkspace('dashboard')
      }
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  async function performAction(path, method, message, confirmMessage = message) {
    if (confirmMessage && !window.confirm(`${confirmMessage}?`)) return
    setError('')
    setNotice('')
    try {
      const result = await api(path, { method })
      setNotice(result.message || message || 'Action completed.')
      await loadWorkspace(page, pageNumbers[page] || 1)
      if (isWorkspacePage && page !== 'dashboard') await loadWorkspace('dashboard')
      if (page === 'network') await loadNetwork()
    } catch (e) { setError(e.message) }
  }

  async function toggleBranchStatus(item) {
    const nextActive = !Boolean(item.is_active)
    const actionWord = nextActive ? 'reactivate' : 'deactivate'
    if (!window.confirm(`${actionWord[0].toUpperCase() + actionWord.slice(1)} ${item.name}?`)) return
    setError('')
    try {
      const result = await api(`/branches/${item.id}`, {
        method: 'PUT',
        body: JSON.stringify({ city_id: item.city_id, name: item.name, code: item.code, address: item.address || '', contact: item.contact || '', is_active: nextActive }),
      })
      setNotice(result.message || `Branch ${nextActive ? 'reactivated' : 'deactivated'}.`)
      await refreshLocations()
    } catch (e) { setError(e.message) }
  }

  const currentRows = records[page] || []
  const filteredRows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return currentRows
    return currentRows.filter(row => Object.values(row || {}).some(value => String(value ?? '').toLowerCase().includes(needle)))
  }, [currentRows, search])
  const cityOptions = useMemo(() => cities.map(city => ({ value: city.id, label: city.province ? `${city.name}, ${city.province}` : city.name })), [cities])
  const branchLabel = branch?.name || (user?.role === 'branch_admin' ? 'My branch' : 'Select a branch')

  if (booting) return <div className="boot-screen"><div className="boot-mark"><Building2 size={28}/></div><LoaderCircle className="spin" size={22}/><p>Restoring your secure session…</p></div>
  if (!user || !token) return <LoginScreen username={username} setUsername={setUsername} password={password} setPassword={setPassword} onSubmit={handleLogin} busy={loginBusy} error={error} />

  return <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : ''}`}>
    <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />
    <aside className="sidebar">
      <div className="brand-row"><div className="brand-mark"><Building2 size={22}/></div><div className="brand-copy"><strong>StayWise</strong><small>HOSTEL NETWORK</small></div><button className="mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><X size={17}/></button></div>
      <div className="nav-group-label">OVERVIEW</div>
      <nav className="nav-list">
        <NavItem item={{ id: 'network', label: 'Network overview', icon: Globe2 }} active={page === 'network'} onClick={goTo} />
        {isSuperAdmin && <NavItem item={{ id: 'locations', label: 'Cities & branches', icon: MapPin }} active={page === 'locations'} onClick={goTo} />}
      </nav>
      <div className="nav-divider" />
      <div className="nav-group-label">BRANCH WORKSPACE</div>
      <nav className="nav-list">
        {WORKSPACE_NAV.map(item => <NavItem key={item.id} item={item} active={page === item.id} onClick={goTo} disabled={!activeBranchId} badge={item.id === 'leaves' && dashboard?.pending_leaves > 0 ? dashboard.pending_leaves : null} />)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="connection-card"><span className="connection-led"/><div><strong>API workspace</strong><small>Authenticated · Live data</small></div><Wifi size={17}/></div>
      <div className="profile-card"><div className="profile-avatar">{initials(user)}</div><div className="profile-meta"><strong>{user.full_name || user.username}</strong><small>{isSuperAdmin ? 'Head office · Super admin' : 'Branch administrator'}</small></div><button title="Sign out" onClick={signOut} className="logout-button"><LogOut size={16}/></button></div>
    </aside>

    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left"><button className="menu-button" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}><Menu size={19}/></button><div className="breadcrumb"><span>StayWise</span><ChevronRight size={14}/><strong>{PAGE_LABELS[page] || (page === 'network' ? 'Network overview' : page === 'locations' ? 'Cities & branches' : page)}</strong></div></div>
        <div className="topbar-tools">
          {isSuperAdmin && <label className="branch-switcher"><Building2 size={16}/><select value={activeBranchId} onChange={e => { const id = e.target.value; setActiveBranchId(id); if (id) setPage('dashboard'); else setPage('network') }} aria-label="Select branch"><option value="">Choose branch workspace</option>{branches.filter(item => item.is_active).map(item => <option key={item.id} value={item.id}>{item.name} · {item.city}</option>)}</select><ChevronDown size={14}/></label>}
          <span className="api-status"><span/> API connected</span><div className="top-avatar">{initials(user)}</div>
        </div>
      </header>

      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">{page === 'network' ? 'MULTI-BRANCH OPERATIONS' : page === 'locations' ? 'NETWORK CONFIGURATION' : `${branchLabel.toUpperCase()} · OPERATIONS`}</div><h1>{page === 'network' ? 'Network overview' : page === 'locations' ? 'Cities & branches' : page === 'dashboard' ? 'Branch dashboard' : PAGE_LABELS[page] || 'Workspace'}</h1><p>{page === 'network' ? 'High-level occupancy and capacity across active branches.' : page === 'locations' ? 'Configure locations, open branches, and manage branch administrator accounts.' : page === 'dashboard' ? `A live snapshot of ${branchLabel.toLowerCase()} operations.` : TABLE_CONFIG[page]?.description || 'Manage branch records securely from one workspace.'}</p></div><div className="heading-actions"><button className="btn btn-secondary" onClick={reloadCurrent} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''}/><span>Refresh</span></button>{isSuperAdmin && page === 'locations' && <button className="btn btn-primary" onClick={() => { setForm({ name: '', province: '', country: 'Pakistan' }); setModal({ kind: 'city' }) }}><Plus size={16}/> Add city</button>}</div></div>

        {error && <Alert type="error" message={error} onClose={() => setError('')} />}
        {notice && <Alert type="success" message={notice} onClose={() => setNotice('')} />}

        {page === 'network' && <NetworkPage data={network} loading={loading} user={user} cityFilter={cityFilter} setCityFilter={setCityFilter} cities={cities} onOpenBranch={id => { setActiveBranchId(String(id)); setPage('dashboard') }} onRefresh={loadNetwork} />}
        {page === 'locations' && isSuperAdmin && <LocationsPage cities={cities} branches={branches} loading={loading} onAddBranch={() => { setForm({ city_id: cities[0]?.id ? String(cities[0].id) : '', name: '', code: '', address: '', contact: '' }); setModal({ kind: 'branch' }) }} onAddCity={() => { setForm({ name: '', province: '', country: 'Pakistan' }); setModal({ kind: 'city' }) }} onAddAdmin={item => { setForm({ username: '', password: '', full_name: '' }); setModal({ kind: 'admin', branchId: item.id, branchName: item.name }) }} onViewAdmins={openBranchAdmins} onEditBranch={openBranchEdit} onToggleStatus={toggleBranchStatus} />}
        {isWorkspacePage && !activeBranchId && <ChooseBranch branches={branches} onChoose={id => { setActiveBranchId(String(id)); setPage('dashboard') }} />}
        {page === 'dashboard' && activeBranchId && <DashboardPage stats={dashboard} students={records.students || []} rooms={records.rooms || []} loading={loading} branchName={dashboard?.branch_name || branchLabel} onNavigate={goTo} onAddStudent={() => openRecordCreate('students')} onAddRoom={() => openRecordCreate('rooms')} />}
        {WORKSPACE_PAGES.includes(page) && activeBranchId && <RecordsPage page={page} rows={filteredRows} totalVisible={filteredRows.length} search={search} setSearch={setSearch} loading={loading} pagination={pagination[page]} pageNumber={pageNumbers[page] || 1} onPageChange={next => loadWorkspace(page, next)} onCreate={() => page === 'allocations' ? openAllocationForm() : page === 'attendance' ? openAttendanceForm('out') : openRecordCreate(page)} onCreateAllocation={openAllocationForm} onCreateAttendance={openAttendanceForm} onAction={performAction} onEditStudent={openStudentEdit} onViewBeds={openRoomBeds} scopedPath={scopedPath} />}

        <footer className="footer"><span><Building2 size={14}/> StayWise Hostel Management</span><span>React · Flask REST API · MySQL</span></footer>
      </div>
    </main>

    {modal && <Modal title={modalTitle(modal)} subtitle={modalSubtitle(modal)} onClose={() => setModal(null)}>
      {modal.kind === 'admins-list' ? <BranchAdminsList admins={modal.admins} loading={modal.loading} error={modal.error} onClose={() => setModal(null)} onEdit={admin => { setError(''); setForm({ username: admin.username, full_name: admin.full_name || '', password: '' }); setModal({ kind: 'admin-edit', branchId: modal.branchId, branchName: modal.branchName, adminId: admin.id, isActive: Boolean(admin.is_active) }) }} /> : <form onSubmit={submitModal}>
        {modal.kind === 'record' && <FormFields fields={FORM_CONFIG[modal.entity].fields} form={form} setForm={setForm} students={lookups.students} />}
        {modal.kind === 'city' && <FormFields fields={[{ key: 'name', label: 'City name', required: true }, { key: 'province', label: 'Province / region' }, { key: 'country', label: 'Country' }]} form={form} setForm={setForm} />}
        {modal.kind === 'branch' && <><FormFields fields={[{ key: 'city_id', label: 'City', type: 'select', required: true, options: cityOptions }, { key: 'name', label: 'Branch / hostel name', required: true }, { key: 'code', label: 'Branch code', required: true, placeholder: 'e.g. ISB-F7' }, { key: 'address', label: 'Address', type: 'textarea' }, { key: 'contact', label: 'Contact number' }]} form={form} setForm={setForm} />{modal.mode === 'edit' && <label className="active-toggle"><input type="checkbox" checked={modal.isActive} onChange={e => setModal(old => ({ ...old, isActive: e.target.checked }))}/> Branch is active</label>}</>}
        {modal.kind === 'admin' && <FormFields fields={[{ key: 'full_name', label: 'Administrator full name' }, { key: 'username', label: 'Username', required: true }, { key: 'password', label: 'Temporary password (8+ characters)', type: 'password', required: true, minLength: 8 }]} form={form} setForm={setForm} />}
        {modal.kind === 'admin-edit' && <><FormFields fields={[{ key: 'full_name', label: 'Administrator full name' }, { key: 'username', label: 'Username', required: true }, { key: 'password', label: 'New password (blank = keep current, 8+ characters)', type: 'password', minLength: 8 }]} form={form} setForm={setForm} /><label className="active-toggle"><input type="checkbox" checked={modal.isActive} onChange={e => setModal(old => ({ ...old, isActive: e.target.checked }))}/> Account is active (can log in)</label></>}
        {modal.kind === 'allocation' && <>
          <FormFields fields={[{ key: 'student_id', label: 'Student', type: 'student', required: true }, { key: 'room_id', label: 'Room', type: 'select', required: true, options: lookups.rooms.map(room => ({ value: room.id, label: `Room ${room.room_number} · Floor ${room.floor}` })) }, { key: 'bed_id', label: 'Available bed', type: 'select', required: true, options: lookups.beds.filter(bed => !form.room_id || String(bed.room_id) === String(form.room_id)).map(bed => ({ value: bed.bed_id, label: `Room ${bed.room_number} · ${bed.bed_name}` })) }]} form={form} setForm={setForm} students={lookups.students} />
          <p className="form-hint">Only available beds are shown. The API validates that the student and bed belong to this branch.</p>
        </>}
        {modal.kind === 'attendance' && <>
          <FormFields fields={[{ key: 'student_id', label: 'Student', type: 'student', required: true }, ...(modal.mode === 'out' ? [{ key: 'purpose', label: 'Purpose', required: true, placeholder: 'e.g. Market, family visit' }, { key: 'remarks', label: 'Remarks (optional)', type: 'textarea' }] : [])]} form={form} setForm={setForm} students={lookups.students} />
          <p className="form-hint">{modal.mode === 'out' ? 'Marking OUT starts an active attendance record. Mark the same student IN when they return.' : 'The API closes the active OUT record for this student.'}</p>
        </>}
        <div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setModal(null)}>Cancel</button><button className="btn btn-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle size={16} className="spin"/> : <Check size={16}/>} {saving ? 'Saving…' : modal.kind === 'record' && modal.mode === 'edit' ? 'Save changes' : modal.kind === 'branch' && modal.mode === 'edit' ? 'Save branch' : 'Save record'}</button></div>
      </form>}
    </Modal>}

    {roomBedModal && <Modal title={`Room ${roomBedModal.room.room_number} · beds`} subtitle={`Floor ${roomBedModal.room.floor} · ${roomBedModal.room.capacity} capacity`} onClose={() => setRoomBedModal(null)}>
      {roomBedModal.loading ? <div className="modal-loading"><LoaderCircle className="spin" size={20}/> Loading bed inventory…</div> : roomBedModal.error ? <Alert type="error" message={roomBedModal.error}/> : <div className="bed-grid">{roomBedModal.beds.map(bed => <div key={bed.id} className={`bed-chip ${bed.status === 'Available' ? 'is-available' : 'is-occupied'}`}><BedDouble size={17}/><span><strong>{bed.bed_name}</strong><small>{bed.status}</small></span></div>)}{!roomBedModal.beds.length && <div className="empty-inline">No bed records returned.</div>}</div>}
      <div className="modal-footer"><button className="btn btn-secondary" onClick={() => setRoomBedModal(null)}>Close</button></div>
    </Modal>}
  </div>
}

function LoginScreen({ username, setUsername, password, setPassword, onSubmit, busy, error }) {
  return <div className="login-screen"><div className="login-decoration decor-one"/><div className="login-decoration decor-two"/><section className="login-card"><div className="login-logo"><div className="brand-mark"><Building2 size={25}/></div><div><strong>StayWise</strong><small>HOSTEL MANAGEMENT</small></div></div><div className="login-copy"><div className="eyebrow"><ShieldCheck size={14}/> SECURE ADMIN ACCESS</div><h1>Welcome back.</h1><p>Sign in to manage your hostel operations and branch network.</p></div>{error && <Alert type="error" message={error} />}
    <div className="default-login-note"><strong>Local demo login</strong><span>Username: <code>superadmin</code></span><span>Password: <code>admin123</code></span><span>Branch admins: <code>hosteladmin</code> / <code>password1</code></span><small>Created automatically by the backend. Only the Super Admin can change branch-admin logins. Local/demo use only.</small></div><form onSubmit={onSubmit} className="login-form"><label>Username<div className="input-with-icon"><CircleUserRound size={17}/><input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} placeholder="Enter your username" required autoFocus/></div></label><label>Password<div className="input-with-icon"><KeyRound size={17}/><input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password" required/></div></label><button className="btn btn-primary login-submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin"/> : <ShieldCheck size={17}/>} {busy ? 'Signing in…' : 'Sign in securely'}</button></form><div className="login-footer"><span><span className="connection-led"/> Token-protected API</span><span>Flask + MySQL</span></div></section><div className="login-footnote">Hostel operations · One connected network · Branch-level privacy</div></div>
}

function NavItem({ item, active, onClick, disabled = false, badge }) {
  const Icon = item.icon
  return <button className={`nav-item ${active ? 'active' : ''} ${disabled ? 'is-disabled' : ''}`} onClick={() => !disabled && onClick(item.id)} disabled={disabled}><Icon size={18}/><span>{item.label}</span>{badge && <em>{badge}</em>}{active && <span className="active-rail"/>}</button>
}

function Alert({ type = 'error', message, onClose }) {
  if (!message) return null
  const Icon = type === 'success' ? CircleCheck : AlertCircle
  return <div className={`alert ${type}`}><Icon size={18}/><span>{message}</span>{onClose && <button onClick={onClose} aria-label="Dismiss message"><X size={16}/></button>}</div>
}

function NetworkPage({ data, loading, user, cityFilter, setCityFilter, cities, onOpenBranch, onRefresh }) {
  const totals = data?.totals || {}
  const rows = (data?.branches || []).filter(branch => !cityFilter || String(branch.city_id) === String(cityFilter))
  const stats = [
    { label: 'Active branches', value: totals.branches, detail: 'Open locations', icon: Building2, tone: 'indigo' },
    { label: 'Residents', value: totals.total_students, detail: 'Across the network', icon: GraduationCap, tone: 'blue' },
    { label: 'Available beds', value: totals.available_beds, detail: `of ${numberText(totals.total_beds)} total beds`, icon: BedDouble, tone: 'green' },
    { label: 'Occupied beds', value: totals.occupied_beds, detail: 'Current occupancy', icon: Activity, tone: 'amber' },
  ]
  return <>
    <section className="network-banner"><div className="network-banner-copy"><div className="banner-icon"><Network size={20}/></div><div><span className="banner-kicker">HOSTEL NETWORK</span><h2>One view. Every location.</h2><p>Explore branch capacity and occupancy without exposing private resident records across locations.</p></div></div><div className="banner-decoration"><div className="orb orb-a"/><div className="orb orb-b"/><div className="banner-ring ring-one"/><div className="banner-ring ring-two"/></div></section>
    <div className="stats-grid network-stats">{stats.map(stat => <StatCard key={stat.label} stat={stat}/>)}</div>
    <section className="panel records-panel"><div className="panel-heading records-heading"><div><h2>Branch performance</h2><p>{rows.length} active location{rows.length === 1 ? '' : 's'} · occupancy counts only</p></div><div className="record-controls"><label className="filter-box"><Filter size={15}/><select value={cityFilter} onChange={e => setCityFilter(e.target.value)}><option value="">All cities</option>{cities.map(city => <option key={city.id} value={city.id}>{city.name}</option>)}</select><ChevronDown size={13}/></label><button className="btn btn-secondary" onClick={onRefresh} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''}/> Refresh</button></div></div>
      <div className="table-wrap"><table><thead><tr><th>Branch</th><th>City</th><th>Students</th><th>Rooms</th><th>Beds availability</th><th>Occupancy</th><th/></tr></thead><tbody>{loading && !rows.length ? <tr><td colSpan="7" className="table-empty">Loading network…</td></tr> : rows.length ? rows.map(item => {
        const percent = item.total_beds ? Math.round((item.occupied_beds / item.total_beds) * 100) : 0
        return <tr key={item.branch_id} className={item.is_your_branch ? 'your-branch-row' : ''}><td><div className="branch-name-cell"><span className="branch-icon"><Building2 size={17}/></span><span><strong>{item.branch_name}</strong><small>{item.code}{item.is_your_branch ? ' · Your branch' : ''}</small></span></div></td><td>{item.city}</td><td><strong>{numberText(item.total_students)}</strong></td><td>{numberText(item.total_rooms)} <span className="muted-inline">({numberText(item.free_rooms)} free)</span></td><td><div className="bed-summary"><strong>{numberText(item.available_beds)}</strong><span> / {numberText(item.total_beds)}</span></div><div className="mini-progress"><span style={{ width: `${item.total_beds ? Math.round((item.available_beds / item.total_beds) * 100) : 0}%` }}/></div></td><td><div className="occupancy-cell"><span>{percent}%</span><small>{numberText(item.occupied_beds)} occupied</small></div></td><td className="table-action-cell">{user?.role === 'super_admin' || item.is_your_branch ? <button className="small-action" onClick={() => onOpenBranch(item.branch_id)}>{item.is_your_branch ? 'My branch' : 'Open branch'} <ChevronRight size={14}/></button> : <span className="restricted-label"><ShieldCheck size={13}/> Summary only</span>}</td></tr>
      }) : <tr><td colSpan="7" className="table-empty">No active branches found for this city. Try another filter or create a branch.</td></tr>}</tbody></table></div>
      <div className="table-footnote"><ShieldCheck size={14}/> Branch administrators can view counts for other branches, but private student and operational records remain branch-scoped.</div>
    </section>
  </>
}

function LocationsPage({ cities, branches, loading, onAddBranch, onAddCity, onAddAdmin, onViewAdmins, onEditBranch, onToggleStatus }) {
  return <>
    <div className="stats-grid locations-stats"><StatCard stat={{ label: 'Registered cities', value: cities.length, detail: 'Network locations', icon: MapPin, tone: 'indigo' }}/><StatCard stat={{ label: 'Total branches', value: branches.length, detail: 'Active and inactive', icon: Building2, tone: 'blue' }}/><StatCard stat={{ label: 'Active branches', value: branches.filter(item => Boolean(item.is_active)).length, detail: 'Accepting operations', icon: CircleCheck, tone: 'green' }}/><StatCard stat={{ label: 'Admin accounts', value: 'Managed per branch', detail: 'Use branch account action', icon: UserCog, tone: 'amber', isText: true }}/></div>
    <section className="panel records-panel"><div className="panel-heading records-heading"><div><h2>Branch directory</h2><p>Manage locations and branch administrator access.</p></div><div className="record-controls"><button className="btn btn-secondary" onClick={onAddCity}><Plus size={15}/> Add city</button><button className="btn btn-primary" onClick={onAddBranch} disabled={!cities.length}><Plus size={15}/> Add branch</button></div></div>
      <div className="table-wrap"><table><thead><tr><th>Branch</th><th>City</th><th>Branch code</th><th>Contact</th><th>Status</th><th>Actions</th></tr></thead><tbody>{loading && !branches.length ? <tr><td colSpan="6" className="table-empty">Loading branch directory…</td></tr> : branches.length ? branches.map(item => <tr key={item.id}><td><div className="branch-name-cell"><span className="branch-icon"><House size={17}/></span><span><strong>{item.name}</strong><small>{item.address || 'No address added'}</small></span></div></td><td>{item.city || cities.find(city => city.id === item.city_id)?.name || '—'}</td><td><span className="code-pill">{item.code}</span></td><td>{item.contact || '—'}</td><td><Status value={item.is_active ? 'Active' : 'Inactive'}/></td><td><div className="row-actions"><button className="icon-btn" title="Edit branch" onClick={() => onEditBranch(item)}><Pencil size={14}/></button><button className="small-action" onClick={() => onViewAdmins(item)}><Users size={13}/> Admins</button><button className="small-action" onClick={() => onAddAdmin(item)}><UserCog size={13}/> Add admin</button><button className={`icon-btn ${item.is_active ? 'danger' : 'good'}`} title={item.is_active ? 'Deactivate branch' : 'Reactivate branch'} onClick={() => onToggleStatus(item)}>{item.is_active ? <CircleX size={14}/> : <CircleCheck size={14}/>}</button></div></td></tr>) : <tr><td colSpan="6" className="table-empty">No branches yet. Add a city first, then create its first branch.</td></tr>}</tbody></table></div>
      <div className="table-footnote"><ShieldCheck size={14}/> Head-office actions are only shown to super administrators. Branch accounts can access detailed records from their assigned branch.</div>
    </section>
    <section className="city-card-grid"><div className="section-caption"><div><h2>City directory</h2><p>Group branches by city and province.</p></div><span>{cities.length} cities</span></div>{cities.length ? cities.map(city => <article className="city-card" key={city.id}><div className="city-card-top"><div className="city-card-icon"><MapPin size={18}/></div><span className="count-pill">{city.branches || 0} branches</span></div><h3>{city.name}</h3><p>{[city.province, city.country].filter(Boolean).join(' · ') || 'Region not specified'}</p></article>) : <div className="empty-inline">No cities configured.</div>}</section>
  </>
}

function DashboardPage({ stats, students, rooms, loading, branchName, onNavigate, onAddStudent, onAddRoom }) {
  const statCards = stats ? [
    { label: 'Total students', value: stats.total_students, detail: 'Registered residents', icon: GraduationCap, tone: 'indigo' },
    { label: 'Total rooms', value: stats.total_rooms, detail: `${numberText(stats.available_rooms)} with free beds`, icon: Building2, tone: 'blue' },
    { label: 'Beds available', value: stats.available_beds, detail: `of ${numberText(stats.total_beds)} total beds`, icon: BedDouble, tone: 'green' },
    { label: 'Currently outside', value: stats.students_outside, detail: 'Active OUT attendance', icon: ArrowUpFromLine, tone: 'amber' },
    { label: 'Pending leaves', value: stats.pending_leaves, detail: 'Awaiting a decision', icon: CalendarDays, tone: 'violet' },
    { label: 'Visitors inside', value: stats.visitors_inside, detail: 'Not checked out yet', icon: UserRound, tone: 'teal' },
  ] : []
  const occupancy = stats?.total_beds ? Math.round((stats.occupied_beds / stats.total_beds) * 100) : 0
  return <>
    <section className="welcome-banner"><div className="welcome-copy"><span className="banner-kicker"><Sparkles size={13}/> BRANCH SNAPSHOT</span><h2>Good to see you.</h2><p>Here is the latest activity and space availability at <strong>{branchName}</strong>.</p><div className="welcome-actions"><button className="btn btn-white" onClick={onAddStudent}><Plus size={15}/> Add student</button><button className="btn btn-glass" onClick={() => onNavigate('allocations')}>Manage allocations <ChevronRight size={15}/></button></div></div><div className="welcome-visual"><div className="visual-building building-large"><div/><div/><div/><div/><div/><div/></div><div className="visual-building building-small"><div/><div/><div/><div/></div><div className="visual-ground"/></div></section>
    <div className="section-caption"><div><h2>Today's overview</h2><p>Numbers reported by the selected branch API.</p></div><span className="live-label"><span/> Live metrics</span></div>
    <div className="stats-grid branch-stats">{statCards.length ? statCards.map(stat => <StatCard key={stat.label} stat={stat}/>) : <div className="empty-state">{loading ? 'Loading branch statistics…' : 'Choose a branch to view statistics.'}</div>}</div>
    <div className="dashboard-grid">
      <section className="panel"><div className="panel-heading"><div><h2>Recent residents</h2><p>Most recent students returned by the API.</p></div><button className="text-button" onClick={() => onNavigate('students')}>View students <ChevronRight size={15}/></button></div><div className="table-wrap"><table><thead><tr><th>Student</th><th>Gender</th><th>Contact</th></tr></thead><tbody>{loading && !students.length ? <tr><td colSpan="3" className="table-empty">Loading residents…</td></tr> : students.length ? [...students].slice(-5).reverse().map(student => <tr key={student.id}><td><div className="resident-cell"><span>{fullName(student).split(/\s+/).map(x => x[0]).slice(0,2).join('').toUpperCase()}</span><div><strong>{fullName(student)}</strong><small>Resident ID #{student.id}</small></div></div></td><td>{student.gender}</td><td>{student.contact || '—'}</td></tr>) : <tr><td colSpan="3" className="table-empty">No resident records yet.</td></tr>}</tbody></table></div><div className="panel-bottom-link"><button onClick={onAddStudent}><Plus size={15}/> Register a new resident</button></div></section>
      <section className="panel room-panel"><div className="panel-heading"><div><h2>Room availability</h2><p>Bed inventory summary.</p></div><button className="text-button" onClick={() => onNavigate('rooms')}>View rooms <ChevronRight size={15}/></button></div><div className="room-overview"><div className="donut-wrap"><div className="donut" style={{ '--progress': `${occupancy * 3.6}deg` }}><div><strong>{occupancy}%</strong><small>occupied</small></div></div></div><div className="donut-legend"><div><span className="legend-dot occupied-dot"/><span>Occupied beds</span><strong>{numberText(stats?.occupied_beds)}</strong></div><div><span className="legend-dot available-dot"/><span>Available beds</span><strong>{numberText(stats?.available_beds)}</strong></div><div><span className="legend-dot neutral-dot"/><span>Total capacity</span><strong>{numberText(stats?.total_beds)}</strong></div></div></div><div className="mini-room-list">{rooms.slice(0, 4).map(room => <div className="mini-room-row" key={room.id}><span className="mini-room-symbol"><DoorOpen size={16}/></span><span><strong>Room {room.room_number}</strong><small>Floor {room.floor} · {room.gender}</small></span><span className="mini-room-count">{room.available_beds}/{room.total_beds}<small>free</small></span></div>)}{!rooms.length && <div className="empty-inline">No rooms configured.</div>}</div><div className="panel-bottom-link"><button onClick={onAddRoom}><Plus size={15}/> Add a room and generate beds</button></div></section>
    </div>
    <section className="panel shortcut-panel"><div className="panel-heading"><div><h2>Quick actions</h2><p>Jump into the tasks most often used by wardens.</p></div></div><div className="shortcut-grid"><Shortcut icon={ClipboardCheck} title="Allocate a bed" detail="Assign a resident to an available bed" onClick={() => onNavigate('allocations')}/><Shortcut icon={CalendarDays} title="Review leaves" detail="Approve or reject pending requests" onClick={() => onNavigate('leaves')}/><Shortcut icon={ArrowUpFromLine} title="Attendance" detail="Record a resident going out or returning" onClick={() => onNavigate('attendance')}/><Shortcut icon={UserRound} title="Visitor register" detail="Log visitors and check them out" onClick={() => onNavigate('visitors')}/></div></section>
  </>
}

function StatCard({ stat }) {
  const Icon = stat.icon
  return <article className={`stat-card ${stat.tone || 'indigo'}`}><div className="stat-top"><span>{stat.label}</span><div className="stat-icon"><Icon size={18}/></div></div><strong className={`stat-value ${stat.isText ? 'text-value' : ''}`}>{stat.isText ? stat.value : numberText(stat.value)}</strong><div className="stat-foot">{stat.detail}</div></article>
}

function RecordsPage({ page, rows, totalVisible, search, setSearch, loading, pagination, pageNumber, onPageChange, onCreate, onCreateAllocation, onCreateAttendance, onAction, onEditStudent, onViewBeds, scopedPath }) {
  const config = TABLE_CONFIG[page]
  const canSearch = !['attendance'].includes(page)
  const totalPages = pagination?.pages || 1
  const first = totalVisible ? ((pageNumber - 1) * (pagination?.limit || PAGE_SIZE)) + 1 : 0
  const last = totalVisible ? first + totalVisible - 1 : 0
  const pageTitles = { students: 'Add student', rooms: 'Add room', allocations: 'New allocation', services: 'Add service', visitors: 'Register visitor', leaves: 'New leave request', attendance: 'Record movement' }
  return <section className="panel records-panel"><div className="panel-heading records-heading"><div><h2>{config.title} records</h2><p>{pagination?.total != null ? `${numberText(pagination.total)} total records` : `${totalVisible} records shown`}</p></div><div className="record-controls">{canSearch && <label className="search-box"><Search size={16}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder={`Search ${config.title.toLowerCase()}…`} aria-label={`Search ${config.title}`}/>{search && <button onClick={() => setSearch('')} aria-label="Clear search"><X size={14}/></button>}</label>}{page === 'attendance' && <><button className="btn btn-secondary" onClick={() => onCreateAttendance('in')}><ArrowDownToLine size={15}/> Mark IN</button><button className="btn btn-primary" onClick={() => onCreateAttendance('out')}><ArrowUpFromLine size={15}/> Mark OUT</button></>}{page === 'allocations' ? <button className="btn btn-primary" onClick={onCreateAllocation}><Plus size={16}/> Allocate bed</button> : !['attendance'].includes(page) && <button className="btn btn-primary" onClick={onCreate}><Plus size={16}/>{pageTitles[page]}</button>}</div></div>
    {page === 'allocations' && <div className="info-strip"><BedDouble size={16}/><span>Each resident can have one active allocation. Checkout frees the bed for the next resident.</span></div>}
    {page === 'rooms' && <div className="info-strip"><ShieldCheck size={16}/><span>Creating a room automatically creates the number of beds specified as its capacity.</span></div>}
    {page === 'attendance' && <div className="info-strip"><Clock3 size={16}/><span>A resident cannot have more than one open OUT record. Use Mark IN when they return.</span></div>}
    <div className="table-wrap"><table><thead><tr>{config.columns.map(([key, label]) => <th key={key}>{label}</th>)}<th className="actions-head">Actions</th></tr></thead><tbody>{loading && !rows.length ? <tr><td colSpan={config.columns.length + 1} className="table-empty"><LoaderCircle size={18} className="spin"/> Loading records…</td></tr> : rows.length ? rows.map(row => <tr key={row.id}>{config.columns.map(([key]) => <td key={key}>{key === 'status' ? <Status value={row[key]}/> : key === 'name' && page === 'services' ? <strong>{row[key]}</strong> : key.endsWith('_date') || ['check_in', 'check_out', 'out_time', 'in_time', 'allocated_date'].includes(key) ? dateText(row[key]) : row[key] == null || row[key] === '' ? '—' : row[key]}</td>)}<td><div className="row-actions">{page === 'students' && <><button className="icon-btn" title="Edit student" onClick={() => onEditStudent(row)}><Pencil size={15}/></button><button className="icon-btn danger" title="Delete student" onClick={() => onAction(scopedPath(`/students/${row.id}`), 'DELETE', `Delete student ${row.id}`, `Delete student ${fullName(row) || row.id}`)}><Trash2 size={15}/></button></>}{page === 'rooms' && <button className="small-action" onClick={() => onViewBeds(row)}><Eye size={14}/> View beds</button>}{page === 'allocations' && row.status === 'Active' && <button className="small-action action-warn" onClick={() => onAction(scopedPath(`/allocations/${row.id}/checkout`), 'PATCH', 'Allocation checked out', `Check out ${row.student_name} from room ${row.room_number}`)}><LogOut size={14}/> Checkout</button>}{page === 'visitors' && row.status === 'CheckedIn' && <button className="small-action action-warn" onClick={() => onAction(scopedPath(`/visitors/${row.id}/checkout`), 'PATCH', 'Visitor checked out', `Check out visitor ${row.visitor_name}`)}><LogOut size={14}/> Checkout</button>}{page === 'leaves' && row.status === 'Pending' && <><button className="icon-btn good" title="Approve leave" onClick={() => onAction(scopedPath(`/leaves/${row.id}/approve`), 'PATCH', 'Leave approved', `Approve leave request #${row.id}`)}><Check size={16}/></button><button className="icon-btn danger" title="Reject leave" onClick={() => onAction(scopedPath(`/leaves/${row.id}/reject`), 'PATCH', 'Leave rejected', `Reject leave request #${row.id}`)}><X size={16}/></button></>}{!['students', 'rooms'].includes(page) && !(page === 'allocations' && row.status === 'Active') && !(page === 'visitors' && row.status === 'CheckedIn') && !(page === 'leaves' && row.status === 'Pending') && <span className="muted-dash">—</span>}</div></td></tr>) : <tr><td colSpan={config.columns.length + 1} className="table-empty">{search ? 'No records match this search.' : 'No records found yet. Use the action above to add one.'}</td></tr>}</tbody></table></div>
    {pagination && <div className="pagination-row"><span>Showing {first}–{last} of {numberText(pagination.total)} records</span><div><button className="pagination-button" disabled={pageNumber <= 1 || loading} onClick={() => onPageChange(pageNumber - 1)}><ChevronLeft size={16}/> Previous</button><span className="page-indicator">Page {pageNumber} of {Math.max(totalPages, 1)}</span><button className="pagination-button" disabled={pageNumber >= totalPages || loading} onClick={() => onPageChange(pageNumber + 1)}>Next <ChevronRight size={16}/></button></div></div>}
    <div className="table-footnote"><ShieldCheck size={14}/> Requests are sent to the authenticated API for the selected branch. The server remains responsible for permissions and validation.</div>
  </section>
}

function FormFields({ fields, form, setForm, students = [] }) {
  return <div className="form-grid">{fields.map(field => {
    const value = form[field.key] ?? ''
    let options = field.options || []
    if (field.type === 'student') options = students.map(student => ({ value: student.id, label: `#${student.id} · ${fullName(student)}${student.contact ? ` · ${student.contact}` : ''}` }))
    return <label key={field.key} className={field.type === 'textarea' ? 'field-span' : ''}>{field.label}{field.required && <span className="required-mark">*</span>}{field.type === 'textarea' ? <textarea required={field.required} rows="3" value={value} placeholder={field.placeholder || ''} onChange={e => setForm(old => ({ ...old, [field.key]: e.target.value }))}/> : field.type === 'select' || field.type === 'student' ? <div className="select-wrap"><select required={field.required} value={value} onChange={e => setForm(old => ({ ...old, [field.key]: e.target.value, ...(field.key === 'room_id' ? { bed_id: '' } : {}) }))}><option value="">Select {field.label.toLowerCase()}</option>{options.map(option => typeof option === 'object' ? <option key={option.value} value={option.value}>{option.label}</option> : <option key={option} value={option}>{option}</option>)}</select><ChevronDown size={14}/></div> : <input type={field.type || 'text'} required={field.required} min={field.min} max={field.max} minLength={field.minLength} value={value} placeholder={field.placeholder || ''} onChange={e => setForm(old => ({ ...old, [field.key]: e.target.value }))}/>}</label>
  })}</div>
}

function Modal({ title, subtitle, onClose, children }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}><section className="modal" role="dialog" aria-modal="true" aria-label={title}><div className="modal-header"><div><h2>{title}</h2><p>{subtitle}</p></div><button className="icon-btn" onClick={onClose} aria-label="Close dialog"><X size={17}/></button></div><div className="modal-body">{children}</div></section></div>
}

function modalTitle(modal) {
  if (modal.kind === 'record') return `${modal.mode === 'edit' ? 'Edit' : 'Add'} ${FORM_CONFIG[modal.entity]?.title || 'record'}`
  if (modal.kind === 'city') return 'Add city'
  if (modal.kind === 'branch') return modal.mode === 'edit' ? 'Edit branch' : 'Create branch'
  if (modal.kind === 'admin') return `Create branch admin`
  if (modal.kind === 'admins-list') return 'Branch administrator accounts'
  if (modal.kind === 'admin-edit') return 'Edit branch admin login'
  if (modal.kind === 'allocation') return 'Allocate a bed'
  if (modal.kind === 'attendance') return modal.mode === 'out' ? 'Mark student OUT' : 'Mark student IN'
  return 'Edit record'
}
function modalSubtitle(modal) {
  if (modal.kind === 'record' && modal.entity === 'rooms') return 'A bed is created automatically for each capacity place.'
  if (modal.kind === 'record' && modal.mode === 'edit') return 'Update the existing student details.'
  if (modal.kind === 'record') return `Fields marked with * are required.`
  if (modal.kind === 'city') return 'Add a city to organize hostel branches.'
  if (modal.kind === 'branch') return modal.mode === 'edit' ? 'Update branch details and active status.' : 'Create a branch inside a city in the network.'
  if (modal.kind === 'admin') return `Set up login access for ${modal.branchName || 'this branch'}. Passwords must contain at least 8 characters.`
  if (modal.kind === 'admin-edit') return `Change the login for ${modal.branchName || 'this branch'}. Only the Super Admin can do this. Leave the password blank to keep it.`
  if (modal.kind === 'admins-list') return `Accounts with access to ${modal.branchName || 'this branch'}. Password hashes are never shown.`
  if (modal.kind === 'allocation') return 'Choose a resident and an available bed in the selected branch.'
  if (modal.kind === 'attendance') return modal.mode === 'out' ? 'Record when a resident leaves the hostel.' : 'Record a resident returning to the hostel.'
  return ''
}

function BranchAdminsList({ admins, loading, error, onClose, onEdit }) {
  return <>
    {error && <Alert type="error" message={error} />}
    {loading ? <div className="modal-loading"><LoaderCircle className="spin" size={20}/> Loading administrator accounts…</div> : error ? null : <div className="admin-list">{admins.map(admin => <div className="admin-row" key={admin.id}><div className="admin-list-avatar"><UserCog size={16}/></div><div className="admin-row-copy"><strong>{admin.full_name || admin.username}</strong><small>@{admin.username} · Created {dateText(admin.created_at)}</small></div><Status value={admin.is_active ? 'Active' : 'Inactive'}/><button type="button" className="btn btn-secondary" onClick={() => onEdit(admin)}><Pencil size={14}/> Edit login</button></div>)}{!admins.length && <div className="empty-inline">No branch admin accounts have been created.</div>}</div>}
    <div className="modal-footer"><button className="btn btn-secondary" onClick={onClose}>Close</button></div>
  </>
}

function ChooseBranch({ branches, onChoose }) {
  const active = branches.filter(item => item.is_active)
  return <section className="choose-branch"><div className="choose-branch-icon"><Building2 size={24}/></div><div className="section-caption"><div><h2>Choose a branch workspace</h2><p>Select a branch to access its resident and room records. Your API role determines which branches you can open.</p></div></div><div className="choose-branch-grid">{active.map(item => <button className="branch-choice" key={item.id} onClick={() => onChoose(item.id)}><div className="branch-choice-icon"><Building2 size={19}/></div><div><strong>{item.name}</strong><small>{item.city} · {item.code}</small><span>{item.address || 'Address not added'}</span></div><ChevronRight size={17}/></button>)}{!active.length && <div className="empty-state">No active branches are available. Create a city and branch from Cities & branches first.</div>}</div></section>
}

function Shortcut({ icon: Icon, title, detail, onClick }) {
  return <button className="shortcut-item" onClick={onClick}><span className="shortcut-icon"><Icon size={18}/></span><span><strong>{title}</strong><small>{detail}</small></span><ChevronRight size={16}/></button>
}

function Status({ value }) {
  const status = String(value ?? 'Unknown')
  const lower = status.toLowerCase()
  let tone = 'neutral'
  if (['active', 'available', 'approved', 'checkedin', 'in'].includes(lower)) tone = 'success'
  if (['pending', 'outside'].includes(lower)) tone = 'warning'
  if (['rejected', 'checked-out', 'checkedout', 'full', 'occupied', 'inactive'].includes(lower)) tone = 'danger'
  return <span className={`status status-${tone}`}><span/>{status}</span>
}
