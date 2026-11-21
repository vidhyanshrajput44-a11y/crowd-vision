import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { TaskItem, LayoutZoneData, VenueLayout } from '../types';
import { api } from '../services/api';

interface TaskContextType {
  tasks: TaskItem[];
  activeTask: TaskItem | null;
  activeZones: LayoutZoneData[];
  isLoading: boolean;
  error: string | null;
  selectTask: (taskId: string) => Promise<void>;
  refreshTasks: () => Promise<void>;
  createTask: (data: {
    name: string;
    description?: string;
    location?: string;
    state?: string;
    layout_id?: string;
    layout_snapshot?: any;
    video_config?: any;
    analysis_settings?: any;
    notes?: string;
  }) => Promise<TaskItem>;
  updateTask: (taskId: string, data: Partial<TaskItem>) => Promise<TaskItem>;
  duplicateTask: (taskId: string) => Promise<TaskItem>;
  deleteTask: (taskId: string) => Promise<void>;
  changeTaskState: (taskId: string, state: string, reason?: string) => Promise<TaskItem>;
  clearError: () => void;
}

const TaskContext = createContext<TaskContextType | undefined>(undefined);

export const TaskProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [activeTask, setActiveTask] = useState<TaskItem | null>(null);
  const [activeZones, setActiveZones] = useState<LayoutZoneData[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const syncActiveZones = (task: TaskItem | null) => {
    if (!task) {
      setActiveZones([]);
      return;
    }
    const snapshot = task.layout_snapshot;
    if (snapshot && snapshot.zones_data && snapshot.zones_data.length > 0) {
      setActiveZones(snapshot.zones_data);
    } else {
      setActiveZones([]);
    }
  };

  const refreshTasks = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const list = await api.getTasks();
      setTasks(list);

      // Keep active task updated or pick Railway CCTV analysis first
      if (list.length > 0) {
        setActiveTask((prev) => {
          if (!prev) {
            const demoTask = list.find((t) => t.name === 'Railway CCTV analysis');
            const target = demoTask || list[0];
            syncActiveZones(target);
            return target;
          }
          const updated = list.find((t) => t.id === prev.id) || list[0];
          syncActiveZones(updated);
          return updated;
        });
      } else {
        setActiveTask(null);
        setActiveZones([]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch tasks');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshTasks();
  }, [refreshTasks]);

  const selectTask = async (taskId: string) => {
    try {
      setIsLoading(true);
      const task = await api.getTask(taskId);
      setActiveTask(task);
      syncActiveZones(task);
    } catch (err: any) {
      setError(err.message || `Failed to select task ${taskId}`);
    } finally {
      setIsLoading(false);
    }
  };

  const createTask = async (data: {
    name: string;
    description?: string;
    location?: string;
    state?: string;
    layout_id?: string;
    layout_snapshot?: any;
    video_config?: any;
    analysis_settings?: any;
    notes?: string;
  }): Promise<TaskItem> => {
    try {
      setIsLoading(true);
      setError(null);
      const created = await api.createTask(data);
      setTasks((prev) => [created, ...prev]);
      setActiveTask(created);
      syncActiveZones(created);
      return created;
    } catch (err: any) {
      setError(err.message || 'Failed to create task');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const updateTask = async (taskId: string, data: Partial<TaskItem>): Promise<TaskItem> => {
    try {
      setError(null);
      const updated = await api.updateTask(taskId, data);
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (activeTask?.id === taskId) {
        setActiveTask(updated);
        syncActiveZones(updated);
      }
      return updated;
    } catch (err: any) {
      setError(err.message || 'Failed to update task');
      throw err;
    }
  };

  const duplicateTask = async (taskId: string): Promise<TaskItem> => {
    try {
      setIsLoading(true);
      setError(null);
      const duplicated = await api.duplicateTask(taskId);
      setTasks((prev) => [duplicated, ...prev]);
      setActiveTask(duplicated);
      syncActiveZones(duplicated);
      return duplicated;
    } catch (err: any) {
      setError(err.message || 'Failed to duplicate task');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const deleteTask = async (taskId: string): Promise<void> => {
    try {
      setIsLoading(true);
      setError(null);
      await api.deleteTask(taskId);
      const remaining = tasks.filter((t) => t.id !== taskId);
      setTasks(remaining);
      if (activeTask?.id === taskId) {
        const next = remaining.length > 0 ? remaining[0] : null;
        setActiveTask(next);
        syncActiveZones(next);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to delete task');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const changeTaskState = async (taskId: string, state: string, reason?: string): Promise<TaskItem> => {
    try {
      setError(null);
      const updated = await api.changeTaskState(taskId, state, reason);
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (activeTask?.id === taskId) {
        setActiveTask(updated);
        syncActiveZones(updated);
      }
      return updated;
    } catch (err: any) {
      setError(err.message || 'Failed to change task state');
      throw err;
    }
  };

  return (
    <TaskContext.Provider
      value={{
        tasks,
        activeTask,
        activeZones,
        isLoading,
        error,
        selectTask,
        refreshTasks,
        createTask,
        updateTask,
        duplicateTask,
        deleteTask,
        changeTaskState,
        clearError: () => setError(null),
      }}
    >
      {children}
    </TaskContext.Provider>
  );
};

export const useTaskContext = (): TaskContextType => {
  const context = useContext(TaskContext);
  if (!context) {
    throw new Error('useTaskContext must be used within a TaskProvider');
  }
  return context;
};
