// CivicLens - Global Application State Context
//
// Owns theme/language/city preferences, the real auth session (custom
// profile, and the citizen's complaint list. Guest Mode is the only path
// that stays fully local/offline — everything else is backed by real
// Express + Postgres backend — see /server/src/db/schema.sql).

import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DARK_THEME, LIGHT_THEME } from '../constants/theme';
import {
  getTranslation,
  LANGUAGES,
  getCityName,
  getCityState,
  getHelplineInfo,
} from '../constants/translations';
import {
  loadComplaints,
  saveNewComplaint,
  addNoteToComplaint as addNoteToComplaintService,
} from '../services/trackingService';
import { ALL_PUBLIC_AUTHORITIES } from '../data/departmentsData';
import { refreshLearnedWeights } from '../services/aiService';
import {
  backendReady,
  getCurrentSession,
  onAuthStateChange,
  fetchProfile,
  upsertProfile,
  signOut as authSignOut,
} from '../services/authService';

const AppContext = createContext();

const PREFS_STORAGE_KEY = '@civiclens_app_prefs_v3';
const GUEST_PROFILE_KEY = '@civiclens_guest_profile_v1';

const DEFAULT_CITIZEN_PROFILE = {
  name: '',
  phone: '',
  email: '',
  address: '',
  city: 'Bengaluru',
  pincode: '',
  isLoggedIn: false,
};

const DEFAULT_OFFICIAL_PROFILE = {
  deptId: '',
  deptName: '',
  officerId: '',
  name: '',
  designation: '',
  phone: '',
  email: '',
  jurisdiction: '',
  isLoggedIn: false,
};

export const AppContextProvider = ({ children }) => {
  // 1. Theme State (Dark / Light)
  const [themeMode, setThemeMode] = useState('dark');
  const theme = themeMode === 'dark' ? DARK_THEME : LIGHT_THEME;

  // 2. Language State (7 Indian languages)
  const [language, setLanguageState] = useState('en');

  // 3. City Selection
  const [selectedCity, setSelectedCity] = useState('bengaluru');

  // 4. Role State ('citizen' | 'official')
  const [userRole, setUserRole] = useState('citizen');

  // 5. Real Auth State (custom backend, not Supabase)
  const [session, setSession] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [isGuestMode, setIsGuestMode] = useState(false);
  const isLoggedIn = Boolean(session) || isGuestMode;
  const currentUserId = session?.user?.id || null;

  // 6. Citizen Profile State (populated from public.profiles once signed in)
  const [userProfile, setUserProfileState] = useState(DEFAULT_CITIZEN_PROFILE);

  // 7. Government Official Profile State
  const [officialProfile, setOfficialProfileState] = useState(DEFAULT_OFFICIAL_PROFILE);

  // 8. Grievances / Complaints State
  const [complaints, setComplaints] = useState([]);
  const [loadingComplaints, setLoadingComplaints] = useState(true);

  const authSubRef = useRef(null);

  // ---- Bootstrapping: preferences + real session -----------------
  useEffect(() => {
    const initialize = async () => {
      try {
        const savedPrefs = await AsyncStorage.getItem(PREFS_STORAGE_KEY);
        if (savedPrefs) {
          const prefs = JSON.parse(savedPrefs);
          if (prefs.themeMode) setThemeMode(prefs.themeMode);
          if (prefs.language) setLanguageState(prefs.language);
          if (prefs.selectedCity) setSelectedCity(prefs.selectedCity);
          if (prefs.userRole) setUserRole(prefs.userRole);
        }

        const existingSession = backendReady ? await getCurrentSession() : null;
        if (existingSession) {
          setSession(existingSession);
          await hydrateProfileFromSession(existingSession);
        } else {
          const guestFlag = await AsyncStorage.getItem(GUEST_PROFILE_KEY);
          if (guestFlag) {
            setIsGuestMode(true);
            setUserProfileState((prev) => ({ ...prev, ...JSON.parse(guestFlag), isLoggedIn: true }));
          }
        }
      } catch (err) {
        console.log('App initialization error:', err.message);
      } finally {
        setAuthLoading(false);
      }
    };

    initialize();
    refreshLearnedWeights();

    if (backendReady) {
      const subscription = onAuthStateChange(async (newSession) => {
        setSession(newSession);
        if (newSession) {
          setIsGuestMode(false);
          await hydrateProfileFromSession(newSession);
        }
      });
      authSubRef.current = subscription;
    }

    return () => authSubRef.current?.unsubscribe?.();
  }, []);

  // Reload complaints whenever the effective user changes (real login, guest, or logout)
  useEffect(() => {
    const refreshComplaints = async () => {
      setLoadingComplaints(true);
      const list = await loadComplaints(currentUserId);
      setComplaints(list);
      setLoadingComplaints(false);
    };
    refreshComplaints();
  }, [currentUserId, isGuestMode]);

  const hydrateProfileFromSession = async (activeSession) => {
    const userId = activeSession?.user?.id;
    if (!userId) return;
    const { profile } = await fetchProfile(userId);
    const authUser = activeSession.user;

    if (profile?.role === 'official') {
      setUserRole('official');
      const dept = ALL_PUBLIC_AUTHORITIES.find((d) => d.id === profile.department_id);
      setOfficialProfileState({
        deptId: profile.department_id || '',
        deptName: dept?.name || '',
        officerId: profile.officer_id || '',
        name: profile.full_name || '',
        designation: profile.designation || '',
        phone: profile.phone || authUser.phone || '',
        email: authUser.email || '',
        jurisdiction: profile.jurisdiction || '',
        isLoggedIn: true,
      });
    } else {
      setUserRole('citizen');
      setUserProfileState({
        name: profile?.full_name || authUser.user_metadata?.full_name || 'Citizen',
        phone: profile?.phone || authUser.phone || '',
        email: authUser.email || '',
        address: profile?.address || '',
        city: profile?.city || 'Bengaluru',
        pincode: profile?.pincode || '',
        isLoggedIn: true,
      });
    }
  };

  // Theme Toggler
  const toggleTheme = async () => {
    const newMode = themeMode === 'dark' ? 'light' : 'dark';
    setThemeMode(newMode);
    await savePreferences({ themeMode: newMode });
  };

  // Language Setter
  const setLanguage = async (newLang) => {
    setLanguageState(newLang);
    await savePreferences({ language: newLang });
  };

  // City Setter
  const setCity = async (newCity) => {
    setSelectedCity(newCity);
    await savePreferences({ selectedCity: newCity });
  };

  // Save Preferences
  const savePreferences = async (newPrefs) => {
    try {
      const currentPrefs = { themeMode, language, selectedCity, userRole, ...newPrefs };
      await AsyncStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(currentPrefs));
    } catch (err) {
      console.log('Error saving preferences:', err.message);
    }
  };

  // Citizen Profile Update — writes through to the real `profiles` table
  const updateUserProfile = async (newProfile) => {
    const updated = { ...userProfile, ...newProfile };
    setUserProfileState(updated);

    if (currentUserId && backendReady) {
      await upsertProfile(currentUserId, {
        role: 'citizen',
        full_name: updated.name,
        phone: updated.phone,
        address: updated.address,
        city: updated.city,
        pincode: updated.pincode,
      });
    } else if (isGuestMode) {
      await AsyncStorage.setItem(GUEST_PROFILE_KEY, JSON.stringify(updated));
    }
  };

  /**
   * Called after AuthScreen has already completed a real sign-in
   * (password / magic link / phone OTP) and a session exists. This just
   * makes sure the citizen's profile row reflects any extra details (name,
   * address, city) collected on the sign-up form.
   */
  const completeCitizenProfile = async (profileData) => {
    if (!currentUserId) return { success: false, error: 'No active session.' };
    const { profile, error } = await upsertProfile(currentUserId, {
      role: 'citizen',
      full_name: profileData.name,
      phone: profileData.phone,
      address: profileData.address,
      city: profileData.city,
      pincode: profileData.pincode,
    });
    if (error) return { success: false, error };
    setUserRole('citizen');
    setUserProfileState((prev) => ({ ...prev, ...profileData, isLoggedIn: true }));
    return { success: true, profile };
  };

  /**
   * Called after a real sign-in for an official. Persists their
   * department/designation onto the shared profiles table.
   */
  const completeOfficialProfile = async (officialData) => {
    if (!currentUserId) return { success: false, error: 'No active session.' };
    const targetDept = ALL_PUBLIC_AUTHORITIES.find((d) => d.id === officialData.deptId);
    const { profile, error } = await upsertProfile(currentUserId, {
      role: 'official',
      full_name: officialData.name,
      department_id: officialData.deptId,
      officer_id: officialData.officerId,
      designation: officialData.designation,
      jurisdiction: officialData.jurisdiction,
    });
    if (error) return { success: false, error };
    setUserRole('official');
    setOfficialProfileState((prev) => ({
      ...prev,
      ...officialData,
      deptName: targetDept ? targetDept.name : prev.deptName,
      isLoggedIn: true,
    }));
    return { success: true, profile };
  };

  // Guest / Demo Login — explicitly local-only, never synced to the cloud
  const loginAsGuest = async () => {
    setIsGuestMode(true);
    setUserRole('citizen');
    const guestProfile = { ...DEFAULT_CITIZEN_PROFILE, name: 'Guest Citizen', isLoggedIn: true };
    setUserProfileState(guestProfile);
    await AsyncStorage.setItem(GUEST_PROFILE_KEY, JSON.stringify(guestProfile));
  };

  // Logout / Reset
  const logout = async () => {
    try {
      if (session) await authSignOut();
      setSession(null);
      setIsGuestMode(false);
      setUserRole('citizen');
      setUserProfileState(DEFAULT_CITIZEN_PROFILE);
      setOfficialProfileState(DEFAULT_OFFICIAL_PROFILE);
      setComplaints([]);
      await AsyncStorage.removeItem(GUEST_PROFILE_KEY);
    } catch (err) {
      console.log('Error logging out:', err.message);
    }
  };

  // Add Grievance — single canonical shape used by every screen + the DB layer
  const addComplaint = async (complaintData) => {
    try {
      const localId = isGuestMode || !currentUserId ? `CIVIC-${Date.now().toString().slice(-6)}` : undefined;
      const newGrievance = {
        id: localId,
        status: 'Submitted',
        dateFiled: new Date().toISOString(),
        citizenPhone: userProfile.phone || '',
        citizenEmail: userProfile.email || '',
        citizenName: userProfile.name || 'Concerned Citizen',
        timeline: [
          { stage: 'Grievance Submitted', date: 'Today', done: true },
          { stage: 'Acknowledged by Ward', date: 'Pending (1-2 days)', done: false },
          { stage: 'Nodal Officer Assigned', date: 'Pending', done: false },
          { stage: 'Inspection & Repair', date: 'Pending', done: false },
          { stage: 'Verified & Resolved', date: 'Pending', done: false },
        ],
        notes: [`Formal draft generated via CivicLens AI on ${new Date().toLocaleDateString('en-IN')}`],
        canEscalate: false,
        stage: 1,
        slaDays: 30,
        ...complaintData,
      };

      const result = await saveNewComplaint(newGrievance, currentUserId);
      const saved = result.complaint || newGrievance;
      setComplaints((prev) => [saved, ...prev]);
      return { success: true, grievance: saved, offlineOnly: result.offlineOnly };
    } catch (err) {
      console.log('Error adding complaint:', err.message);
      return { success: false, error: err.message };
    }
  };

  const addComplaintNote = async (complaintId, noteText) => {
    const result = await addNoteToComplaintService(complaintId, noteText, currentUserId);
    if (result.success) {
      setComplaints((prev) =>
        prev.map((c) =>
          c.id === complaintId
            ? { ...c, notes: result.complaints.find((rc) => rc.id === complaintId)?.notes || c.notes }
            : c
        )
      );
    }
    return result;
  };

  // Official Status Update (local optimistic update; remote write handled by
  // OfficialPortalScreen via trackingService.updateComplaintStatusRemote so
  // RLS can enforce that only the routed department's officer can do this)
  const updateComplaintStatus = (complaintId, newStatus, officerRemarks, atrFile) => {
    setComplaints((prev) =>
      prev.map((c) => {
        if (c.id === complaintId) {
          const isResolved = newStatus === 'Resolved' || newStatus === 'Closed';
          return {
            ...c,
            status: newStatus,
            stage: isResolved ? 5 : newStatus === 'In Progress' ? 4 : 3,
            officerRemarks: officerRemarks || c.officerRemarks,
            atrFile: atrFile || c.atrFile,
            updatedAt: new Date().toISOString(),
            history: [
              ...(c.history || []),
              {
                status: newStatus,
                timestamp: new Date().toISOString(),
                officer: officialProfile.name || 'Nodal Officer',
                remarks: officerRemarks || `Status updated to ${newStatus}`,
              },
            ],
          };
        }
        return c;
      })
    );
    return { success: true };
  };

  // Translation Helper function
  const t = (key) => getTranslation(language, key);

  return (
    <AppContext.Provider
      value={{
        theme,
        themeMode,
        toggleTheme,
        language,
        setLanguage,
        languagesList: LANGUAGES,
        t,
        selectedCity,
        setCity,
        getCityName: (id) => getCityName(id, language),
        getCityState: (id) => getCityState(id, language),
        getHelplineInfo: (id) => getHelplineInfo(id, language),
        backendReady,
        authLoading,
        isLoggedIn,
        isGuestMode,
        loginAsGuest,
        userRole,
        setUserRole,
        userProfile,
        updateUserProfile,
        officialProfile,
        completeCitizenProfile,
        completeOfficialProfile,
        logout,
        complaints,
        loadingComplaints,
        addComplaint,
        addComplaintNote,
        updateComplaintStatus,
        currentUserId,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => useContext(AppContext);
