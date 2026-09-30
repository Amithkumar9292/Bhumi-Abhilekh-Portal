import React, { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, Plus, Eye, ChevronLeft, ChevronRight, ArrowUpDown } from 'lucide-react';
import { getMockListItems } from '../mock/mockData';
import { formatRelative, STATUS_LABELS, LAND_USE_LABELS } from '../utils/formatters';
import type { LandRecordListItem } from '../types/land';

const PAGE_SIZE = 20;
type SortKey = keyof LandRecordListItem;

const STATUS_OPTIONS = ['', 'PENDING', 'UNDER_REVIEW', 'VERIFIED', 'REJECTED', 'ARCHIVED'] as const;
const LAND_USE_OPTIONS = ['', 'AGRICULTURAL', 'RESIDENTIAL', 'COMMERCIAL', 'FOREST', 'INDUSTRIAL', 'WASTELAND'] as const;

export function LandRecordsPage() {
  const all = useMemo(() => getMockListItems(), []);
  const [q,     setQ]     = useState('');
  const [status,setStatus]= useState('');
  const [landUse,setLandUse]=useState('');
  const [page,  setPage]  = useState(1);
  const [sort,  setSort]  = useState<{key:SortKey;dir:'asc'|'desc'}>({key:'created_at',dir:'desc'});

  const filtered = useMemo(() => {
    let d = all;
    if (q) { const ql=q.toLowerCase(); d=d.filter(r=>r.khasra_number.toLowerCase().includes(ql)||r.owner_name.toLowerCase().includes(ql)||r.district.toLowerCase().includes(ql)||r.village.toLowerCase().includes(ql)); }
    if (status)  d = d.filter(r => r.status === status);
    if (landUse) d = d.filter(r => r.land_use_type === landUse);
    d = [...d].sort((a,b) => {
      const av = String(a[sort.key]??''), bv = String(b[sort.key]??'');
      return sort.dir==='asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return d;
  }, [all, q, status, landUse, sort]);

  const pages  = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const slice  = filtered.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);
  const safeP  = Math.min(page, pages);

  function toggleSort(key: SortKey) {
    setSort(s => s.key===key ? {...s,dir:s.dir==='asc'?'desc':'asc'} : {key,dir:'asc'});
    setPage(1);
  }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Land Records</div>
          <div className="page-hdr__sub">{filtered.length} records · {all.length} total</div>
        </div>
        <div className="page-hdr__actions">
          <Link to="/intake" className="btn btn--primary btn--md"><Plus size={14}/>New Record</Link>
        </div>
      </div>

      <div className="tbl-wrap">
        {/* Toolbar */}
        <div className="tbl-toolbar">
          <div className="g-search" style={{flex:'1',maxWidth:320}}>
            <Search size={13} className="g-search__icon" style={{color:'var(--text-tertiary)'}}/>
            <input
              className="field__input field__input--icon"
              placeholder="Search khasra no., owner, district…"
              value={q} onChange={e=>{setQ(e.target.value);setPage(1);}}
            />
          </div>
          <select className="field__input" style={{width:150}} value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}>
            <option value="">All Statuses</option>
            {STATUS_OPTIONS.slice(1).map(s=><option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
          <select className="field__input" style={{width:160}} value={landUse} onChange={e=>{setLandUse(e.target.value);setPage(1);}}>
            <option value="">All Land Uses</option>
            {LAND_USE_OPTIONS.slice(1).map(l=><option key={l} value={l}>{LAND_USE_LABELS[l]}</option>)}
          </select>
          {(q||status||landUse) && (
            <button className="btn btn--ghost btn--sm" onClick={()=>{setQ('');setStatus('');setLandUse('');setPage(1);}}>
              Clear
            </button>
          )}
        </div>

        {/* Table */}
        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                {([['khasra_number','Khasra No.'],['owner_name','Owner'],['district','District'],['village','Village'],['area_hectares','Area (ha)'],['land_use_type','Land Use'],['status','Status'],['created_at','Submitted']] as [SortKey,string][]).map(([k,l])=>(
                  <th key={k} className="sortable" onClick={()=>toggleSort(k)}>
                    <span style={{display:'flex',alignItems:'center',gap:4}}>
                      {l}<ArrowUpDown size={11} style={{opacity:sort.key===k?1:0.35,color:sort.key===k?'var(--color-navy-700)':'inherit'}}/>
                    </span>
                  </th>
                ))}
                <th style={{width:60}}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {slice.length === 0 ? (
                <tr><td colSpan={9}><div className="empty"><div className="empty__icon">🔍</div><div className="empty__title">No records found</div><div className="empty__desc">Try adjusting your search or filters</div></div></td></tr>
              ) : slice.map(r => (
                <tr key={r.id}>
                  <td><Link to={`/land-records/${r.id}`} style={{color:'var(--color-navy-700)',fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)',fontWeight:600}}>{r.khasra_number}</Link></td>
                  <td style={{fontWeight:500}}>{r.owner_name}</td>
                  <td style={{color:'var(--text-secondary)',fontSize:'var(--text-xs)'}}>{r.district}</td>
                  <td style={{color:'var(--text-secondary)',fontSize:'var(--text-xs)'}}>{r.village}</td>
                  <td style={{fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)'}}>{r.area_hectares}</td>
                  <td style={{fontSize:'var(--text-xs)'}}>{LAND_USE_LABELS[r.land_use_type] ?? r.land_use_type}</td>
                  <td><span className={`badge badge--${r.status}`}>{STATUS_LABELS[r.status]}</span></td>
                  <td style={{color:'var(--text-tertiary)',fontSize:'var(--text-xs)'}}>{formatRelative(r.created_at)}</td>
                  <td>
                    <Link to={`/land-records/${r.id}`} className="btn btn--ghost btn--xs"><Eye size={12}/></Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="pagination">
          <div className="pagination__info">
            Showing {Math.min((safeP-1)*PAGE_SIZE+1, filtered.length)}–{Math.min(safeP*PAGE_SIZE, filtered.length)} of {filtered.length}
          </div>
          <div className="pagination__controls">
            <button className="page-btn" onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={safeP===1}><ChevronLeft size={13}/></button>
            {Array.from({length:Math.min(pages,7)},(_,i)=>{
              let pg = i+1;
              if (pages>7) { if (i===0) pg=1; else if (i===6) pg=pages; else pg=Math.max(2,Math.min(pages-1,safeP-3+i)); }
              return <button key={pg} className={`page-btn${safeP===pg?' active':''}`} onClick={()=>setPage(pg)}>{pg}</button>;
            })}
            <button className="page-btn" onClick={()=>setPage(p=>Math.min(pages,p+1))} disabled={safeP===pages}><ChevronRight size={13}/></button>
          </div>
        </div>
      </div>
    </div>
  );
}
