import React, { useState, useEffect } from 'react';
import { Sidebar, NavTab } from './components/layout/Sidebar';
import { Topbar } from './components/layout/Topbar';
import { MonitoringWorkspace } from './views/MonitoringWorkspace';
import { TasksManagementView } from './views/TasksManagementView';
import { LayoutManagementView } from './views/LayoutManagementView';
import { SpatialLayoutBuilder } from './components/layout_builder/SpatialLayoutBuilder';
import { CopilotView } from './views/CopilotView';
import { TaskHistoryView } from './views/TaskHistoryView';
import { AlertsPanel } from './components/alerts/AlertsPanel';
import { ReportsView } from './components/reports/ReportsView';
import { SettingsView } from './views/SettingsView';
import { CreateTaskWizard } from './views/CreateTaskWizard';
import { TaskProvider, useTaskContext } from './context/TaskContext';

import {
  LayoutZoneData,
  AlertItem,
  EventZoneSummary,
  User,
  PredictionItem,
} from './types';
import { api } from './services/api';
import { wsClient } from './services/websocket';

const AppInner: React.FC = () => {
  const { activeTask, refreshTasks } = useTaskContext();

  const [currentTab, setCurrentTab] = useState<NavTab>('monitoring');
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [zoneSummary, setZoneSummary] = useState<EventZoneSummary | null>(null);
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);

  const [isCreateTaskOpen, setIsCreateTaskOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Layout Builder State when editing a specific layout
  const [editingLayoutId, setEditingLayoutId] = useState<string | undefined>(undefined);
  const [editingLayoutZones, setEditingLayoutZones] = useState<LayoutZoneData[] | undefined>(undefined);

  // Initialize Auth
  useEffect(() => {
    const initApp = async () => {
      try {
        if (!api.getToken()) {
          await api.login();
        }
        const user = await api.getMe().catch(() => null);
        if (user) setCurrentUser(user);
      } catch {
        // ignore
      }
    };
    initApp();
  }, []);

  // Sync alerts & summaries when active task changes
  useEffect(() => {
    if (!activeTask) return;

    const loadTaskData = async () => {
      setIsRefreshing(true);
      try {
        const [alts, summary, preds] = await Promise.all([
          api.getAlerts(activeTask.id).catch(() => []),
          api.getZoneSummary(activeTask.id).catch(() => null),
          api.getPredictions(activeTask.id).catch(() => []),
        ]);
        setAlerts(alts);
        if (summary) setZoneSummary(summary);
        if (preds) setPredictions(preds);
      } finally {
        setIsRefreshing(false);
      }
    };

    loadTaskData();

    // Connect WebSocket for live telemetry
    wsClient.connect(activeTask.id);
    const unsubscribe = wsClient.subscribe((data) => {
      if (data.alerts && data.alerts.length > 0) {
        setAlerts((prev) => [...data.alerts, ...prev]);
      }
    });

    return () => {
      unsubscribe();
      wsClient.disconnect();
    };
  }, [activeTask?.id]);

  const handleRefreshAll = async () => {
    if (!activeTask) return;
    setIsRefreshing(true);
    try {
      await refreshTasks();
      const [alts, summary, preds] = await Promise.all([
        api.getAlerts(activeTask.id).catch(() => []),
        api.getZoneSummary(activeTask.id).catch(() => null),
        api.getPredictions(activeTask.id).catch(() => []),
      ]);
      setAlerts(alts);
      if (summary) setZoneSummary(summary);
      if (preds) setPredictions(preds);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#070B14]">
      {/* Dense Surveillance Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={(tab) => {
          if (tab === 'layout-builder') {
            // Reset to clean builder unless editing
            setEditingLayoutId(undefined);
            setEditingLayoutZones(undefined);
          }
          setCurrentTab(tab);
        }}
        onOpenCreateTask={() => setIsCreateTaskOpen(true)}
        alertCount={alerts.filter((a) => a.status === 'ACTIVE').length}
        agentStatus="connected"
      />

      {/* Main Console Body */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header Bar with Task Switcher */}
        <Topbar
          currentUser={currentUser}
          activeAlertCount={alerts.filter((a) => a.status === 'ACTIVE').length}
          onRefresh={handleRefreshAll}
          isRefreshing={isRefreshing}
          onOpenCreateTask={() => setIsCreateTaskOpen(true)}
          onNavigateToTasks={() => setCurrentTab('tasks')}
        />

        {/* Dynamic Page Workspace */}
        <main className="flex-1 overflow-y-auto p-6 scroll-smooth">
          {currentTab === 'monitoring' && (
            <MonitoringWorkspace
              onOpenLayoutBuilder={() => {
                setEditingLayoutId(undefined);
                setEditingLayoutZones(undefined);
                setCurrentTab('layout-builder');
              }}
              onOpenCreateTask={() => setIsCreateTaskOpen(true)}
            />
          )}

          {currentTab === 'tasks' && (
            <TasksManagementView
              onOpenCreateTask={() => setIsCreateTaskOpen(true)}
              onNavigateToMonitoring={() => setCurrentTab('monitoring')}
            />
          )}

          {currentTab === 'layouts' && (
            <LayoutManagementView
              onOpenBuilderForLayout={(layoutId, zones) => {
                setEditingLayoutId(layoutId);
                setEditingLayoutZones(zones);
                setCurrentTab('layout-builder');
              }}
              onCreateTaskWithLayout={() => {
                setIsCreateTaskOpen(true);
              }}
            />
          )}

          {currentTab === 'layout-builder' && (
            <div className="h-[calc(100vh-8rem)]">
              <SpatialLayoutBuilder
                layoutId={editingLayoutId}
                initialZones={editingLayoutZones}
                onSaved={() => {
                  setCurrentTab('layouts');
                }}
              />
            </div>
          )}

          {currentTab === 'copilot' && <CopilotView />}

          {currentTab === 'alerts' && (
            <AlertsPanel
              alerts={alerts}
              onAlertUpdated={handleRefreshAll}
            />
          )}

          {currentTab === 'history' && <TaskHistoryView />}

          {currentTab === 'reports' && (
            <ReportsView eventId={activeTask?.id || ''} />
          )}

          {currentTab === 'settings' && <SettingsView />}
        </main>
      </div>

      {/* 6-Step Task Creation Flow Wizard */}
      <CreateTaskWizard
        isOpen={isCreateTaskOpen}
        onClose={() => setIsCreateTaskOpen(false)}
        onTaskCreated={() => {
          setIsCreateTaskOpen(false);
          setCurrentTab('monitoring');
        }}
      />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <TaskProvider>
      <AppInner />
    </TaskProvider>
  );
};

export default App;
