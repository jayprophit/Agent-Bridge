import React, { useState } from 'react';
import {
  RotateCcw,
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Sun,
  Moon,
  Plus,
  Check,
  Trash2,
  Calendar,
  Tag,
  Kanban,
  List,
  MoreVertical,
  CheckCircle2,
  Sparkles
} from 'lucide-react';
import { TaskItem as ITaskItem } from '../types';
import { INITIAL_TASKS } from '../data/mockData';
import { TaskCompletionTrendChart } from './TaskCompletionTrendChart';
import { TrendingUp, BarChart3, ChevronDown, ChevronUp } from 'lucide-react';

interface InteractivePreviewProps {
  tasks?: ITaskItem[];
  projectName?: string;
}

export const InteractivePreview: React.FC<InteractivePreviewProps> = ({
  tasks: initialTasks,
  projectName = 'Task Manager App',
}) => {
  const [tasks, setTasks] = useState<ITaskItem[]>(initialTasks || INITIAL_TASKS);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskPriority, setNewTaskPriority] = useState<'High' | 'Medium' | 'Low'>('Medium');
  const [filter, setFilter] = useState<'all' | 'active' | 'completed'>('all');
  const [viewMode, setViewMode] = useState<'list' | 'kanban'>('list');
  const [showTrendChart, setShowTrendChart] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 500);
  };

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;

    const newTask: ITaskItem = {
      id: `task-${Date.now()}`,
      title: newTaskTitle.trim(),
      status: 'todo',
      priority: newTaskPriority,
      tag: 'Task',
      dueDate: 'Today',
      assignee: 'You',
    };

    setTasks([newTask, ...tasks]);
    setNewTaskTitle('');
  };

  const handleToggleTask = (id: string) => {
    setTasks(
      tasks.map((t) => {
        if (t.id === id) {
          const newStatus = t.status === 'done' ? 'todo' : 'done';
          return { ...t, status: newStatus };
        }
        return t;
      })
    );
  };

  const handleDeleteTask = (id: string) => {
    setTasks(tasks.filter((t) => t.id !== id));
  };

  const handleMoveStatus = (id: string, status: ITaskItem['status']) => {
    setTasks(tasks.map((t) => (t.id === id ? { ...t, status } : t)));
  };

  const totalCount = tasks.length;
  const activeCount = tasks.filter((t) => t.status !== 'done').length;
  const completedCount = tasks.filter((t) => t.status === 'done').length;
  const highPriorityCount = tasks.filter((t) => t.priority === 'High' && t.status !== 'done').length;

  const filteredTasks = tasks.filter((t) => {
    if (filter === 'all') return true;
    if (filter === 'active') return t.status !== 'done';
    if (filter === 'completed') return t.status === 'done';
    return true;
  });

  return (
    <div className="flex-1 flex flex-col h-full bg-[#080d1a] text-slate-100 overflow-hidden">
      {/* Browser Bar */}
      <div className="h-11 bg-slate-950/90 border-b border-slate-800/80 px-3 flex items-center justify-between text-xs shrink-0 select-none">
        <div className="flex items-center gap-2">
          <button className="p-1 text-slate-500 hover:text-slate-300 transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" />
          </button>
          <button className="p-1 text-slate-500 hover:text-slate-300 transition-colors">
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleRefresh}
            className={`p-1 text-slate-400 hover:text-slate-200 transition-colors ${
              isRefreshing ? 'animate-spin text-blue-400' : ''
            }`}
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* URL Pill */}
        <div className="flex-1 max-w-md mx-3">
          <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-slate-400">http://</span>
            <span className="text-slate-100 font-medium">localhost:5173</span>
            <span className="text-slate-500">/tasks</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* List vs Kanban Toggle */}
          <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800">
            <button
              onClick={() => setViewMode('list')}
              className={`p-1 rounded ${viewMode === 'list' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
              title="List View"
            >
              <List className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('kanban')}
              className={`p-1 rounded ${viewMode === 'kanban' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
              title="Kanban Board View"
            >
              <Kanban className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-[10px] font-bold text-white">
            JD
          </div>
        </div>
      </div>

      {/* App Body - TaskFlow */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 max-w-4xl w-full mx-auto space-y-6">
        {/* Header Branding */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-[0_0_15px_rgba(37,99,235,0.4)]">
              <Check className="w-6 h-6 stroke-[3]" />
            </div>
            <div>
              <h2 className="text-xl font-bold tracking-tight text-white">TaskFlow</h2>
              <p className="text-xs text-slate-400">Stay focused. Get things done.</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTrendChart(!showTrendChart)}
              className={`px-2.5 py-1 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all ${
                showTrendChart
                  ? 'bg-blue-600/20 text-cyan-300 border-blue-500/40 shadow-sm'
                  : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-slate-200'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
              <span>Trends Chart</span>
              {showTrendChart ? (
                <ChevronUp className="w-3 h-3 text-slate-400" />
              ) : (
                <ChevronDown className="w-3 h-3 text-slate-400" />
              )}
            </button>

            <span className="px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-semibold flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Sync Active
            </span>
          </div>
        </div>

        {/* D3.js Task Completion Trends Chart */}
        {showTrendChart && (
          <TaskCompletionTrendChart tasks={tasks} projectName={projectName} />
        )}

        {/* 4 Stat Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center shadow-sm">
            <div className="text-2xl font-black text-blue-400">{totalCount}</div>
            <div className="text-[11px] font-medium text-slate-400 mt-0.5">Total</div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center shadow-sm">
            <div className="text-2xl font-black text-cyan-400">{activeCount}</div>
            <div className="text-[11px] font-medium text-slate-400 mt-0.5">Active</div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center shadow-sm">
            <div className="text-2xl font-black text-emerald-400">{completedCount}</div>
            <div className="text-[11px] font-medium text-slate-400 mt-0.5">Completed</div>
          </div>
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 text-center shadow-sm">
            <div className="text-2xl font-black text-rose-400">{highPriorityCount}</div>
            <div className="text-[11px] font-medium text-slate-400 mt-0.5">High Priority</div>
          </div>
        </div>

        {/* Add Task Bar */}
        <form
          onSubmit={handleAddTask}
          className="flex flex-col sm:flex-row items-center gap-2 p-1.5 bg-slate-900/90 border border-slate-800 rounded-xl shadow-lg"
        >
          <input
            type="text"
            value={newTaskTitle}
            onChange={(e) => setNewTaskTitle(e.target.value)}
            placeholder="What do you want to accomplish?"
            className="flex-1 bg-transparent px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none w-full"
          />

          <div className="flex items-center gap-2 w-full sm:w-auto justify-end px-2">
            <select
              value={newTaskPriority}
              onChange={(e) => setNewTaskPriority(e.target.value as any)}
              className="bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none"
            >
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>

            <button
              type="submit"
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-[0_0_12px_rgba(37,99,235,0.4)] transition-all whitespace-nowrap"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Task</span>
            </button>
          </div>
        </form>

        {/* Filter Pills */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
              filter === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            All ({totalCount})
          </button>
          <button
            onClick={() => setFilter('active')}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
              filter === 'active'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            Active ({activeCount})
          </button>
          <button
            onClick={() => setFilter('completed')}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors ${
              filter === 'completed'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            Completed ({completedCount})
          </button>
        </div>

        {/* Task List Mode */}
        {viewMode === 'list' ? (
          <div className="space-y-2">
            {filteredTasks.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-xs">
                No tasks found in this view.
              </div>
            ) : (
              filteredTasks.map((t) => {
                const isDone = t.status === 'done';
                return (
                  <div
                    key={t.id}
                    className="flex items-center justify-between p-3.5 bg-slate-900/70 hover:bg-slate-900 border border-slate-800 rounded-xl transition-all group"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <button
                        onClick={() => handleToggleTask(t.id)}
                        className={`w-5 h-5 rounded-md border flex items-center justify-center transition-colors ${
                          isDone
                            ? 'bg-blue-600 border-blue-500 text-white'
                            : 'border-slate-600 hover:border-slate-400'
                        }`}
                      >
                        {isDone && <Check className="w-3.5 h-3.5" />}
                      </button>
                      <span
                        className={`text-xs sm:text-sm font-medium truncate ${
                          isDone ? 'line-through text-slate-500' : 'text-slate-200'
                        }`}
                      >
                        {t.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0 ml-3">
                      {/* Priority Tag */}
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          t.priority === 'High'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                            : t.priority === 'Medium'
                            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                            : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        }`}
                      >
                        {t.priority}
                      </span>

                      {/* Category Tag */}
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-slate-800 text-slate-400 hidden sm:inline">
                        {t.tag}
                      </span>

                      {/* Due Date */}
                      <span className="text-[11px] text-slate-500 font-mono hidden md:inline">
                        {t.dueDate}
                      </span>

                      {/* Delete */}
                      <button
                        onClick={() => handleDeleteTask(t.id)}
                        className="p-1 rounded text-slate-500 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete Task"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        ) : (
          /* Kanban Board Mode */
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {[
              { id: 'todo', title: 'To Do', color: 'border-blue-500/40' },
              { id: 'in-progress', title: 'In Progress', color: 'border-amber-500/40' },
              { id: 'review', title: 'Review', color: 'border-purple-500/40' },
              { id: 'done', title: 'Done', color: 'border-emerald-500/40' },
            ].map((col) => {
              const colTasks = tasks.filter((t) => t.status === col.id);
              return (
                <div
                  key={col.id}
                  className={`bg-slate-900/60 border ${col.color} rounded-xl p-3 flex flex-col space-y-3 min-h-[220px]`}
                >
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                    <span className="text-xs font-bold text-slate-200">{col.title}</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">
                      {colTasks.length}
                    </span>
                  </div>

                  <div className="space-y-2 flex-1">
                    {colTasks.map((t) => (
                      <div
                        key={t.id}
                        className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 hover:border-slate-700 space-y-2 shadow-sm"
                      >
                        <div className="text-xs font-medium text-slate-200 leading-snug">
                          {t.title}
                        </div>
                        <div className="flex items-center justify-between text-[10px]">
                          <span
                            className={`px-1.5 py-0.5 rounded ${
                              t.priority === 'High' ? 'text-rose-400 bg-rose-500/10' : 'text-slate-400 bg-slate-800'
                            }`}
                          >
                            {t.priority}
                          </span>
                          <span className="text-slate-500">{t.dueDate}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div className="pt-6 text-center space-y-1 border-t border-slate-800/60 select-none">
          <p className="text-xs italic text-slate-400">
            “Small steps <span className="text-white font-bold not-italic">create big results.</span>”
          </p>
          <p className="text-[10px] text-slate-500 font-mono">
            Built with Aetherius • Running locally
          </p>
        </div>
      </div>
    </div>
  );
};
