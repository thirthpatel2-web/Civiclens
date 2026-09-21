// Background synchronisation while the app is not in the foreground (best effort: the OS decides when it runs).
import * as BackgroundTask from 'expo-background-task';
import * as TaskManager from 'expo-task-manager';
import { draftStore } from './storage.ts';
import { syncAll } from './sync.ts';
import { isOnline } from './SyncContext.tsx';
import { endpoints } from '../api/instance.ts';

export const SYNC_TASK = 'civiclens-sync';

TaskManager.defineTask(SYNC_TASK, async () => {
  try {
    await syncAll({ store: draftStore, api: { uploadEvidence: endpoints.uploadEvidence, transcribe: endpoints.transcribe, createComplaint: endpoints.createComplaint }, isOnline, now: () => new Date() });
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

export async function registerBackgroundSync() {
  if (await TaskManager.isTaskRegisteredAsync(SYNC_TASK)) return;
  await BackgroundTask.registerTaskAsync(SYNC_TASK, { minimumInterval: 15 }); // minutes
}
