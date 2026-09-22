import {useState} from 'react';
import {DateField} from '../../components/DateField';
import {CalendarIcon, SearchIcon} from '../../components/icons';
import type {useMemoryFilters} from './useMemoryFilters';

export function MemoryFilters({state, graph = false}: {state: ReturnType<typeof useMemoryFilters>; graph?: boolean}) {
  const [mode, setMode] = useState<'search' | 'date'>('search');
  const {filters, change, invalid, saveError} = state;
  return <form className={`memory-filters${graph ? ' memory-graph-filters' : ''}`} aria-label={graph ? '图谱筛选' : '记忆筛选'} onSubmit={event => event.preventDefault()}>
    <div className="memory-filter-controls" data-mode={mode}>
      {mode === 'search' ? <input type="search" aria-label="查找记忆内容" placeholder="搜索内容" value={filters.search} onChange={event => change('search', event.target.value)}/> :
        <button type="button" className="control control--icon" aria-label="展开搜索栏" title="展开搜索栏" onClick={() => setMode('search')}><SearchIcon/></button>}
      {mode === 'date' ? <div className="date-range-filter" role="group" aria-label="日期范围">
        <DateField compact label="开始日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.start || null} onChange={date => change('start', date || '')}/>
        <span aria-hidden="true">至</span>
        <DateField compact label="结束日期" emptyLabel="不限" emptyOptionLabel="不限" value={filters.end || null} onChange={date => change('end', date || '')}/>
      </div> : <button type="button" className="control control--icon" aria-label="展开日期范围栏" title="展开日期范围栏" onClick={() => setMode('date')}><CalendarIcon/></button>}
    </div>
    {invalid ? <p role="alert" className="memory-error">开始日期不能晚于结束日期。</p> : null}
    {saveError ? <p role="alert" className="memory-error">{saveError}</p> : null}
  </form>;
}
