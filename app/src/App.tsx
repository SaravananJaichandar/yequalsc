import { useState, useEffect, ReactNode, useCallback, useRef } from 'react';
import {
  Command, Settings, MessageSquare, Layers,
  Upload, Send, Paperclip, AlertTriangle,
  BrainCircuit, LucideIcon,
  Check, X, Plus, FolderOpen, Loader2, WifiOff,
  ChevronDown, ChevronUp, MessageCircle, Trash2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import * as api from './api';
import type { GooseStatus } from './api';
import { invoke } from '@tauri-apps/api/core';

// --- Utility ---
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Types ---
interface WindowFrameProps {
  children: ReactNode;
  darkMode: boolean;
}

interface SidebarProps {
  activeView: string;
  setActiveView: (view: string) => void;
  chatSessions: ChatSession[];
  activeChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewChat: () => void;
  onDeleteChat: (id: string) => void;
}

interface SettingsViewProps {
  darkMode: boolean;
  setDarkMode: (mode: boolean) => void;
}

interface Message {
  id: number;
  type: 'user' | 'bot';
  text: string;
  timestamp: Date;
  sources?: string[];
  memories?: {
    text: string;
    source: string;
    sourceType: string;
    score: number;
  }[];
}

interface NavItem {
  id: string;
  icon: LucideIcon;
  label: string;
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

interface UploadedFile {
  name: string;
  size: number;
  type: 'claude' | 'chatgpt' | 'notes' | 'pdf';
  status: 'pending' | 'processing' | 'done' | 'error';
  progress?: number;
  file?: File;  // Actual file object for upload
  filePath?: string;  // Path after upload
  error?: string;
}

// --- Custom SVG Icons for Services ---
const ClaudeIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
  </svg>
);

const ChatGPTIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"/>
  </svg>
);

const AppleNotesIcon = ({ className }: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/>
  </svg>
);

// --- Components ---

// 1. Layout Container with Window Controls
const WindowFrame = ({ children, darkMode }: WindowFrameProps) => {
  const handleClose = () => invoke('close_window');
  const handleMinimize = () => invoke('minimize_window');
  const handleMaximize = () => invoke('toggle_maximize');

  return (
    <div className={cn(
      "h-screen w-screen flex flex-col overflow-hidden transition-colors duration-300 select-none font-sans",
      darkMode ? "dark bg-[#1e1c36] text-white" : "bg-[#fffffe] text-[#272343]"
    )}>
      <div data-tauri-drag-region className="h-10 flex items-center justify-between px-4 shrink-0 bg-background/50">
        <div className="flex gap-2 group">
          <button
            onClick={handleClose}
            className="w-3 h-3 rounded-full bg-red-500 hover:bg-red-600 transition-colors cursor-pointer flex items-center justify-center group-hover:shadow-[0_0_4px_rgba(239,68,68,0.5)]"
            title="Close"
          />
          <button
            onClick={handleMinimize}
            className="w-3 h-3 rounded-full bg-yellow-500 hover:bg-yellow-600 transition-colors cursor-pointer flex items-center justify-center group-hover:shadow-[0_0_4px_rgba(234,179,8,0.5)]"
            title="Minimize"
          />
          <button
            onClick={handleMaximize}
            className="w-3 h-3 rounded-full bg-green-500 hover:bg-green-600 transition-colors cursor-pointer flex items-center justify-center group-hover:shadow-[0_0_4px_rgba(34,197,94,0.5)]"
            title="Maximize"
          />
        </div>
        <div className="font-orbitron text-xs tracking-[0.2em] opacity-40 font-bold uppercase">
          Private Memory Vault
        </div>
        <div className="w-10"></div>
      </div>
      <div className="flex-1 flex overflow-hidden relative">
        {children}
      </div>
    </div>
  );
};

// 2. Sidebar Component
interface VaultStats {
  totalChunks: number;
  sources: string[];
}

const Sidebar = ({ activeView, setActiveView, chatSessions, activeChatId, onSelectChat, onNewChat, onDeleteChat }: SidebarProps) => {
  const [vaultStats, setVaultStats] = useState<VaultStats>({ totalChunks: 0, sources: [] });
  const [modelReady, setModelReady] = useState(false);
  const [modelDownloading, setModelDownloading] = useState(false);
  const MAX_CHUNKS = 10000; // Arbitrary max for percentage display

  const navItems: NavItem[] = [
    { id: 'chat', icon: MessageSquare, label: 'Memory Stream' },
    { id: 'files', icon: Layers, label: 'Sources' },
    { id: 'ingest', icon: Upload, label: 'Ingest More' },
    { id: 'settings', icon: Settings, label: 'System' },
  ];

  // Fetch vault stats and model status on mount and periodically
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await api.getStats();
        if (response.status === 'ok' && response.stats) {
          setVaultStats({
            totalChunks: response.stats.total_chunks || 0,
            sources: response.stats.sources || []
          });
        }
      } catch (err) {
        console.error('Failed to fetch stats:', err);
      }
    };
    const fetchModelStatus = async () => {
      try {
        const status = await api.getModelStatus();
        setModelReady(status.ready);
        setModelDownloading(status.downloading);
      } catch { /* ignore */ }
    };
    fetchStats();
    fetchModelStatus();
    const interval = setInterval(fetchStats, 10000);
    const modelInterval = setInterval(() => {
      if (!modelReady) fetchModelStatus();
    }, 2000);
    return () => { clearInterval(interval); clearInterval(modelInterval); };
  }, [modelReady]);

  const capacityPercent = Math.min(100, Math.round((vaultStats.totalChunks / MAX_CHUNKS) * 100));

  return (
    <div className="w-16 lg:w-64 flex flex-col border-r border-border/40 bg-background/30 pt-4 pb-4 transition-all duration-300">
      <div className="px-4 mb-6 flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#7f5af0] to-[#2cb67d] flex items-center justify-center shadow-[0_0_15px_rgba(127,90,240,0.3)]">
          <BrainCircuit className="w-5 h-5 text-white" />
        </div>
        <span className="font-orbitron font-bold text-xl hidden lg:block tracking-wide">y=c</span>
      </div>

      {/* Navigation */}
      <nav className="px-2 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveView(item.id)}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group relative",
              activeView === item.id
                ? "bg-primary/10 text-primary shadow-[0_0_10px_rgba(0,120,255,0.1)]"
                : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
            )}
          >
            <item.icon className={cn("w-5 h-5 transition-colors", activeView === item.id ? "text-neon-blue" : "")} />
            <span className="hidden lg:block text-sm font-medium">{item.label}</span>
            {activeView === item.id && (
              <motion.div
                layoutId="activeTab"
                className="absolute left-0 w-1 h-6 bg-neon-blue rounded-r-full"
              />
            )}
          </button>
        ))}
      </nav>

      {/* Chat Sessions Section */}
      <div className="mt-6 flex-1 overflow-hidden flex flex-col hidden lg:flex">
        <div className="px-4 mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Chats</span>
          <button
            onClick={onNewChat}
            className="p-1 rounded hover:bg-secondary/50 text-muted-foreground hover:text-neon-blue transition-colors"
            title="New Chat"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 space-y-1">
          {chatSessions.map((session) => (
            <div
              key={session.id}
              onClick={() => onSelectChat(session.id)}
              className={cn(
                "group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all",
                activeChatId === session.id
                  ? "bg-neon-blue/10 text-neon-blue border border-neon-blue/30"
                  : "hover:bg-secondary/50 text-muted-foreground hover:text-foreground"
              )}
            >
              <MessageCircle className="w-4 h-4 flex-shrink-0" />
              <span className="text-xs truncate flex-1">{session.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteChat(session.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/20 hover:text-red-400 transition-all"
                title="Delete chat"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
          {chatSessions.length === 0 && (
            <div className="text-xs text-muted-foreground/50 text-center py-4">
              No chats yet
            </div>
          )}
        </div>
      </div>

      {/* Model Status */}
      {!modelReady && (
        <div className="px-4 mb-2 hidden lg:block">
          <div className="flex items-center gap-2 text-xs text-muted-foreground/70 px-1">
            <Loader2 className="w-3 h-3 animate-spin text-neon-blue" />
            <span>{modelDownloading ? 'Downloading model...' : 'Loading model...'}</span>
          </div>
        </div>
      )}

      {/* Memory Vault Stats */}
      <div className="px-4 mt-auto hidden lg:block">
        <div className="bg-secondary/50 rounded-xl p-3 border border-border/30">
          <div className="flex justify-between text-xs mb-2 opacity-70">
            <span>Memory Vault</span>
            <span className="font-mono">{vaultStats.totalChunks.toLocaleString()} chunks</span>
          </div>
          <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-neon-blue to-neon-green transition-all duration-500"
              style={{ width: `${Math.max(2, capacityPercent)}%` }}
            />
          </div>
          {vaultStats.sources.length > 0 && (
            <div className="mt-2 text-[10px] text-muted-foreground/60">
              {vaultStats.sources.length} source{vaultStats.sources.length !== 1 ? 's' : ''} indexed
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// 3. Source Card Component (for drag & drop)
interface SourceCardProps {
  id: 'claude' | 'chatgpt' | 'notes';
  name: string;
  description: string;
  icon: ReactNode;
  color: string;
  onFileDrop: (file: File, type: 'claude' | 'chatgpt' | 'notes') => void;
  onMacNotesClick?: () => void;
}

const SourceCard = ({ id, name, description, icon, color, onFileDrop, onMacNotesClick }: SourceCardProps) => {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      onFileDrop(files[0], id);
    }
  }, [id, onFileDrop]);

  const handleClick = () => {
    if (id === 'notes' && onMacNotesClick) {
      onMacNotesClick();
    } else {
      fileInputRef.current?.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onFileDrop(files[0], id);
    }
  };

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      className={cn(
        "relative p-6 rounded-2xl border-2 border-dashed cursor-pointer transition-all duration-300",
        isDragging
          ? `border-${color} bg-${color}/10 scale-105`
          : "border-border/50 hover:border-border bg-secondary/20 hover:bg-secondary/40"
      )}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,.zip"
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="flex flex-col items-center text-center gap-3">
        <div className={cn(
          "w-16 h-16 rounded-2xl flex items-center justify-center transition-all",
          isDragging ? `bg-${color}/20` : "bg-secondary/50"
        )}
        style={{
          backgroundColor: isDragging ? `var(--color-${color})20` : undefined,
          boxShadow: isDragging ? `0 0 20px var(--color-${color})40` : undefined
        }}
        >
          <div className={cn("w-10 h-10", isDragging ? `text-${color}` : "text-muted-foreground")}>
            {icon}
          </div>
        </div>

        <div>
          <h3 className="font-semibold text-sm mb-1">{name}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60 mt-2">
          {id === 'notes' ? (
            <>
              <FolderOpen className="w-3 h-3" />
              <span>Click to import from Notes</span>
            </>
          ) : (
            <>
              <Upload className="w-3 h-3" />
              <span>Drop JSON or click to browse</span>
            </>
          )}
        </div>
      </div>

      {isDragging && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="absolute inset-0 rounded-2xl bg-neon-blue/5 border-2 border-neon-blue flex items-center justify-center"
        >
          <span className="font-orbitron text-neon-blue text-sm">DROP FILE</span>
        </motion.div>
      )}
    </motion.div>
  );
};

// 4. Welcome/Onboarding View with Source Selection
interface OnboardingViewProps {
  onStartIngestion: (files: UploadedFile[]) => void;
}

const OnboardingView = ({ onStartIngestion }: OnboardingViewProps) => {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [showSourceSelector, setShowSourceSelector] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');

  // Check backend health on mount
  useEffect(() => {
    const checkBackend = async () => {
      const isOnline = await api.checkHealth();
      setBackendStatus(isOnline ? 'online' : 'offline');
    };
    checkBackend();
    // Check every 5 seconds
    const interval = setInterval(checkBackend, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleFileDrop = (file: File, type: 'claude' | 'chatgpt' | 'notes') => {
    const newFile: UploadedFile = {
      name: file.name,
      size: file.size,
      type,
      status: 'pending',
      file  // Store actual file for later upload
    };
    setUploadedFiles(prev => [...prev, newFile]);
    console.log(`File added: ${file.name} for ${type}`);
  };

  const handleMacNotesImport = () => {
    const newFile: UploadedFile = {
      name: 'Mac Notes (Direct Import)',
      size: 0,
      type: 'notes',
      status: 'pending'
    };
    setUploadedFiles(prev => [...prev, newFile]);
  };

  const removeFile = (index: number) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const startIngestion = () => {
    console.log('Start Ingestion clicked, files:', uploadedFiles.length);
    if (uploadedFiles.length > 0) {
      onStartIngestion(uploadedFiles);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center w-full h-full p-8 text-center relative overflow-hidden"
    >
      <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_50%_50%,rgba(127,90,240,0.06),transparent_50%)] pointer-events-none" />

      <AnimatePresence mode="wait">
        {!showSourceSelector ? (
          <motion.div
            key="welcome"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex flex-col items-center"
          >
            <motion.h1
              initial={{ y: 20 }} animate={{ y: 0 }}
              className="font-orbitron text-5xl md:text-7xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-[#272343] via-[#7f5af0] to-[#272343] mb-6 drop-shadow-[0_0_10px_rgba(127,90,240,0.3)]"
            >
              y=c
            </motion.h1>

            <p className="text-muted-foreground text-lg max-w-md mb-12 font-light">
              Your private second brain. Ingest your digital life into a secure, searchable memory vault.
            </p>

            <button
              onClick={() => setShowSourceSelector(true)}
              className="group relative px-8 py-3 bg-foreground text-background rounded-full font-medium overflow-hidden transition-all hover:scale-105 active:scale-95"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-neon-blue to-neon-purple opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <span className="relative flex items-center gap-2 group-hover:text-white transition-colors">
                <Upload className="w-4 h-4" />
                Ingest Memories
              </span>
            </button>

            <div className="mt-12 flex items-center gap-2 text-xs text-muted-foreground/60 border border-border/30 px-4 py-2 rounded-full bg-background/20 backdrop-blur-sm">
              <Command className="w-3 h-3" />
              <span>⌥</span>
              <span>Space</span>
              <span className="ml-1">to trigger quick recall</span>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="sources"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="w-full max-w-3xl"
          >
            <h2 className="font-orbitron text-2xl font-bold mb-2">Select Your Sources</h2>
            <p className="text-muted-foreground mb-4">Import your conversations and notes. Drag & drop or click to browse.</p>

            {/* Backend Status */}
            <div className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs mb-6",
              backendStatus === 'online' ? "bg-neon-green/10 text-neon-green" :
              backendStatus === 'offline' ? "bg-red-500/10 text-red-400" :
              "bg-secondary/50 text-muted-foreground"
            )}>
              {backendStatus === 'checking' && <Loader2 className="w-3 h-3 animate-spin" />}
              {backendStatus === 'online' && <span className="w-2 h-2 rounded-full bg-neon-green" />}
              {backendStatus === 'offline' && <WifiOff className="w-3 h-3" />}
              <span>
                {backendStatus === 'checking' ? 'Connecting to backend...' :
                 backendStatus === 'online' ? 'Backend connected' :
                 'Backend offline - start with: python -m backend.yc_server'}
              </span>
            </div>

            {/* Source Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <SourceCard
                id="claude"
                name="Claude"
                description="Import Claude.ai conversations"
                icon={<ClaudeIcon className="w-full h-full" />}
                color="neon-purple"
                onFileDrop={handleFileDrop}
              />
              <SourceCard
                id="chatgpt"
                name="ChatGPT"
                description="Import OpenAI conversations"
                icon={<ChatGPTIcon className="w-full h-full" />}
                color="neon-green"
                onFileDrop={handleFileDrop}
              />
              <SourceCard
                id="notes"
                name="Mac Notes"
                description="Import directly from Notes app"
                icon={<AppleNotesIcon className="w-full h-full" />}
                color="neon-blue"
                onFileDrop={handleFileDrop}
                onMacNotesClick={handleMacNotesImport}
              />
            </div>

            {/* Uploaded Files List */}
            {uploadedFiles.length > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="bg-secondary/30 rounded-xl p-4 mb-6"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium">Ready to Import ({uploadedFiles.length})</span>
                  <button
                    onClick={() => setUploadedFiles([])}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Clear All
                  </button>
                </div>
                <div className="space-y-2">
                  {uploadedFiles.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between bg-background/50 rounded-lg px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        {file.type === 'claude' && <ClaudeIcon className="w-4 h-4 text-neon-purple" />}
                        {file.type === 'chatgpt' && <ChatGPTIcon className="w-4 h-4 text-neon-green" />}
                        {file.type === 'notes' && <AppleNotesIcon className="w-4 h-4 text-neon-blue" />}
                        <span className="text-sm">{file.name}</span>
                        {file.size > 0 && (
                          <span className="text-xs text-muted-foreground">
                            ({(file.size / 1024).toFixed(1)} KB)
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => removeFile(index)}
                        className="text-muted-foreground hover:text-red-500 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {/* Action Buttons */}
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={() => setShowSourceSelector(false)}
                className="px-6 py-2.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Back
              </button>
              <button
                onClick={startIngestion}
                disabled={uploadedFiles.length === 0}
                className={cn(
                  "px-8 py-2.5 rounded-full font-medium transition-all flex items-center gap-2",
                  uploadedFiles.length > 0
                    ? "bg-neon-blue text-white hover:shadow-[0_0_20px_rgba(0,243,255,0.4)] hover:scale-105"
                    : "bg-secondary text-muted-foreground cursor-not-allowed"
                )}
              >
                <BrainCircuit className="w-4 h-4" />
                Start Ingestion
              </button>
            </div>

            {/* Skip Option */}
            <button
              onClick={() => onStartIngestion([])}
              className="mt-6 text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors"
            >
              Skip for now →
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// 5. Ingestion Progress View (Real Progress)
interface IngestionViewProps {
  files: UploadedFile[];
  onFinished: () => void;
}

const IngestionView = ({ files, onFinished }: IngestionViewProps) => {
  const [overallProgress, setOverallProgress] = useState(0);
  const [status, setStatus] = useState<string>('Initializing...');
  const [processedFiles, setProcessedFiles] = useState<UploadedFile[]>(files);
  const [chunksAdded, setChunksAdded] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const processFiles = async () => {
      if (files.length === 0) {
        onFinished();
        return;
      }

      // Track total chunks locally for accurate final count
      let totalChunksAdded = 0;

      try {
        // Reset any stuck ingestion state first
        await api.resetIngestion();

        // Phase 1: Upload files to backend
        setStatus('Uploading files...');
        const uploadedPaths: { type: string; path: string }[] = [];

        for (let i = 0; i < files.length; i++) {
          const file = files[i];

          // Update status
          setProcessedFiles(prev => prev.map((f, idx) =>
            idx === i ? { ...f, status: 'processing', progress: 0 } : f
          ));
          setStatus(`Uploading ${file.name}...`);

          if (file.type === 'notes') {
            // Mac Notes doesn't need upload
            uploadedPaths.push({ type: 'notes', path: '' });
            setProcessedFiles(prev => prev.map((f, idx) =>
              idx === i ? { ...f, status: 'processing', progress: 50 } : f
            ));
          } else if (file.file) {
            // Upload the file
            try {
              const result = await api.uploadFile(file.file, file.type as 'claude' | 'chatgpt');
              uploadedPaths.push({ type: file.type, path: result.file_path });
              setProcessedFiles(prev => prev.map((f, idx) =>
                idx === i ? { ...f, status: 'processing', progress: 50, filePath: result.file_path } : f
              ));
            } catch (uploadError) {
              setProcessedFiles(prev => prev.map((f, idx) =>
                idx === i ? { ...f, status: 'error', error: String(uploadError) } : f
              ));
              continue;
            }
          }

          setOverallProgress(((i + 0.5) / files.length) * 50);
        }

        // Phase 2: Run ingestion for each source type
        setStatus('Processing memories...');
        const sourceTypes = [...new Set(uploadedPaths.map(p => p.type))];

        for (let i = 0; i < sourceTypes.length; i++) {
          const sourceType = sourceTypes[i];
          const sourcePaths = uploadedPaths.filter(p => p.type === sourceType);

          setStatus(`Ingesting ${sourceType} conversations...`);

          // Start ingestion with force=true to override any stuck state
          try {
            await api.startIngestion(
              sourceType as 'claude' | 'chatgpt' | 'notes',
              sourcePaths[0]?.path || undefined,
              true  // force=true to reset any stuck state
            );

            // Poll for progress
            let ingestionActive = true;
            while (ingestionActive) {
              await new Promise(r => setTimeout(r, 500));
              const ingestionStatus = await api.getIngestionStatus();

              if (!ingestionStatus.active) {
                ingestionActive = false;
                // Only show error if there's an actual error AND no chunks were added
                if (ingestionStatus.error && ingestionStatus.chunks_added === 0) {
                  setError(ingestionStatus.error);
                }
                totalChunksAdded += ingestionStatus.chunks_added;
                setChunksAdded(totalChunksAdded);
              }

              // Update file progress for this source type
              // Use chunks_added for smoother progress (ramp 50→95 during processing)
              const chunkProgress = Math.min(95, 50 + Math.log2(1 + (ingestionStatus.chunks_added || 0)) * 5);
              const progressPct = ingestionStatus.active ? chunkProgress : 50 + (i + 1) / sourceTypes.length * 50;
              setOverallProgress(progressPct);

              // Update individual file progress
              setProcessedFiles(prev => prev.map(f => {
                if (f.type === sourceType && f.status === 'processing') {
                  return { ...f, progress: 50 + ingestionStatus.progress / 2 };
                }
                return f;
              }));
            }

            // Mark files of this type as done
            setProcessedFiles(prev => prev.map(f => {
              if (f.type === sourceType && f.status === 'processing') {
                return { ...f, status: 'done', progress: 100 };
              }
              return f;
            }));

          } catch (ingestionError) {
            console.error('Ingestion error:', ingestionError);
            setProcessedFiles(prev => prev.map(f => {
              if (f.type === sourceType && f.status === 'processing') {
                return { ...f, status: 'error', error: String(ingestionError) };
              }
              return f;
            }));
          }
        }

        setStatus(`Complete! Added ${totalChunksAdded} memory chunks.`);
        setOverallProgress(100);
        setTimeout(onFinished, 2000);

      } catch (err) {
        setError(String(err));
        setStatus('Error occurred during ingestion');
      }
    };

    processFiles();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, onFinished]);

  return (
    <div className="flex flex-col items-center justify-center w-full h-full p-8">
      <div className="w-full max-w-md space-y-6">
        {/* Overall Progress */}
        <div className="text-center mb-8">
          <div className="font-orbitron text-4xl font-bold text-neon-blue mb-2">
            {Math.round(overallProgress)}%
          </div>
          <div className="text-sm text-muted-foreground">{status}</div>
        </div>

        {/* Progress Bar */}
        <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-[#7f5af0] to-[#2cb67d] shadow-[0_0_10px_rgba(127,90,240,0.3)]"
            initial={{ width: 0 }}
            animate={{ width: `${overallProgress}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-400">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4" />
              <span className="font-medium">Error</span>
            </div>
            {error}
          </div>
        )}

        {/* File List with Progress */}
        <div className="space-y-3 mt-8">
          {processedFiles.map((file, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                "flex items-center gap-3 p-3 rounded-lg transition-all",
                file.status === 'processing' ? "bg-neon-blue/10 border border-neon-blue/30" :
                file.status === 'done' ? "bg-neon-green/10" :
                file.status === 'error' ? "bg-red-500/10 border border-red-500/30" : "bg-secondary/30"
              )}
            >
              <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-secondary/50">
                {file.type === 'claude' && <ClaudeIcon className="w-5 h-5" />}
                {file.type === 'chatgpt' && <ChatGPTIcon className="w-5 h-5" />}
                {file.type === 'notes' && <AppleNotesIcon className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{file.name}</div>
                {file.status === 'processing' && file.progress !== undefined && (
                  <div className="h-1 w-full bg-secondary rounded-full mt-1 overflow-hidden">
                    <div
                      className="h-full bg-neon-blue transition-all duration-300"
                      style={{ width: `${file.progress}%` }}
                    />
                  </div>
                )}
                {file.status === 'error' && file.error && (
                  <div className="text-xs text-red-400 mt-1 truncate">{file.error}</div>
                )}
              </div>
              <div className="w-6 h-6 flex items-center justify-center">
                {file.status === 'done' && <Check className="w-4 h-4 text-neon-green" />}
                {file.status === 'error' && <X className="w-4 h-4 text-red-400" />}
                {file.status === 'processing' && (
                  <div className="w-4 h-4 border-2 border-neon-blue border-t-transparent rounded-full animate-spin" />
                )}
              </div>
            </motion.div>
          ))}
        </div>

        {/* Chunks Added Counter */}
        {chunksAdded > 0 && (
          <div className="text-center text-sm text-muted-foreground mt-4">
            <span className="text-neon-green font-mono">{chunksAdded}</span> memory chunks created
          </div>
        )}
      </div>
    </div>
  );
};

// 6. Expandable Memory Card Component
const MemoryCard = ({ memory, index }: { memory: { text: string; source: string; sourceType: string; score: number }; index: number }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isLongText = memory.text.length > 300;
  const displayText = isExpanded || !isLongText ? memory.text : memory.text.slice(0, 300) + '...';

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.1 }}
      className="bg-background/60 border border-border/40 rounded-xl p-4 backdrop-blur-sm hover:border-neon-blue/30 transition-colors"
    >
      {/* Memory header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded flex items-center justify-center bg-secondary/50">
            {memory.sourceType === 'claude' && <ClaudeIcon className="w-3 h-3 text-neon-purple" />}
            {memory.sourceType === 'chatgpt' && <ChatGPTIcon className="w-3 h-3 text-neon-green" />}
            {memory.sourceType === 'mac_notes' && <AppleNotesIcon className="w-3 h-3 text-neon-blue" />}
          </div>
          <span className="text-xs text-muted-foreground font-medium truncate max-w-[200px]">
            {memory.source}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground/60 font-mono">
          {Math.round(memory.score * 100)}% match
        </span>
      </div>
      {/* Memory content - selectable */}
      <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap select-text cursor-text">
        {displayText}
      </p>
      {/* Expand/Collapse button */}
      {isLongText && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="mt-2 flex items-center gap-1 text-xs text-neon-blue hover:text-neon-blue/80 transition-colors"
        >
          {isExpanded ? (
            <>
              <ChevronUp className="w-3 h-3" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="w-3 h-3" />
              Show full memory
            </>
          )}
        </button>
      )}
    </motion.div>
  );
};

// 7. Chat View
interface ChatViewProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}

const ChatView = ({ messages, setMessages }: ChatViewProps) => {
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<'Ready' | 'Searching' | 'Processing'>('Ready');
  const [gooseStatus, setGooseStatus] = useState<GooseStatus | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Check Goose status on mount
  useEffect(() => {
    const checkGoose = async () => {
      const status = await api.getGooseStatus();
      setGooseStatus(status);
    };
    checkGoose();
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Check if query is too generic
  const isGenericQuery = (query: string): boolean => {
    const genericPatterns = /^(hi|hello|hey|yo|sup|what's up|howdy|greetings|test|help|ok|yes|no|thanks|thank you|bye|good|bad|nice|cool|okay)$/i;
    const trimmed = query.trim().toLowerCase();
    return genericPatterns.test(trimmed) || trimmed.length < 3;
  };

  // Get contextual response for generic queries
  const getGenericResponse = (query: string): string => {
    const greetings = /^(hi|hello|hey|yo|sup|what's up|howdy|greetings)$/i;
    if (greetings.test(query.trim())) {
      return "Hey there! I'm here to help you search through your memories. Ask me something specific like:\n\n• \"What did we discuss about [topic]?\"\n• \"Find conversations about [keyword]\"\n• \"Remind me about [project name]\"";
    }
    return "I work best with specific queries. Try asking about a topic, project, or keyword from your past conversations. What would you like to find?";
  };

  const handleSend = async () => {
    if (!input.trim()) return;

    const userQuery = input;
    setMessages(prev => [...prev, { id: Date.now(), type: 'user', text: userQuery, timestamp: new Date() }]);
    setInput('');

    // Handle generic queries without searching
    if (isGenericQuery(userQuery)) {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        text: getGenericResponse(userQuery),
        timestamp: new Date()
      }]);
      return;
    }

    setStatus('Searching');

    try {
      // Use askQuestion for LLM-synthesized response (with Goose dyad when available)
      const response = await api.askQuestion(userQuery, 5);

      setStatus('Processing');

      if (response.status === 'ok') {
        // Check if we got a meaningful answer
        if (response.answer && !response.answer.includes("couldn't find any relevant")) {
          let answerText = response.answer;

          // Clean up any Goose session noise from the answer
          answerText = answerText
            .replace(/^execution_mode:.*\n/gm, '')
            .replace(/^task_ids:.*\n/gm, '')
            .replace(/^-32602:.*\n/gm, '')
            .replace(/^starting session.*\n/gm, '')
            .replace(/^session id:.*\n/gm, '')
            .replace(/^working directory:.*\n/gm, '')
            .replace(/^─+\n/gm, '')
            .trim();

          // Extract memories from sources for display
          const memories = response.sources
            .filter(s => s.text && s.text.length > 0)
            .slice(0, 3)
            .map(s => ({
              text: s.text,
              source: s.source.replace(/^(claude|chatgpt):/, ''),
              sourceType: s.source_type,
              score: s.score
            }));

          const sourceNames = response.sources
            .map(s => s.source.replace(/^(claude|chatgpt):/, ''))
            .filter(s => s && s.length > 0)
            .slice(0, 4);

          setMessages(prev => [...prev, {
            id: Date.now() + 1,
            type: 'bot',
            text: answerText,
            timestamp: new Date(),
            memories: memories.length > 0 ? memories : undefined,
            sources: sourceNames.length > 0 ? sourceNames : undefined
          }]);
        } else {
          // No relevant results
          setMessages(prev => [...prev, {
            id: Date.now() + 1,
            type: 'bot',
            text: "I couldn't find any memories matching that query. Try:\n\n• Different keywords\n• More specific topics\n• Names of projects or tools you discussed",
            timestamp: new Date()
          }]);
        }
      } else {
        setMessages(prev => [...prev, {
          id: Date.now() + 1,
          type: 'bot',
          text: `Something went wrong: ${response.answer}`,
          timestamp: new Date()
        }]);
      }
    } catch (err) {
      console.error('Search error:', err);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        type: 'bot',
        text: "I can't reach my memory banks right now. Make sure the backend server is running!",
        timestamp: new Date()
      }]);
    }

    setStatus('Ready');
  };

  return (
    <div className="flex flex-col h-full w-full relative">
      <div className="h-16 border-b border-border/40 flex items-center justify-between px-6 backdrop-blur-sm">
        <div className="flex flex-col">
          <span className="font-orbitron font-bold text-lg">Focus Mode</span>
          <span className="text-xs text-muted-foreground flex items-center gap-1.5">
            <span className={cn(
              "w-2 h-2 rounded-full",
              status === 'Ready' ? "bg-neon-green shadow-[0_0_5px_#0aff68]" :
              status === 'Searching' ? "bg-neon-purple animate-pulse" : "bg-neon-blue animate-pulse"
            )} />
            {status === 'Searching' ? (gooseStatus?.configured ? 'Thinking with Goose...' : 'Searching memories...') :
             status === 'Processing' ? 'Synthesizing...' :
             (gooseStatus?.configured ? 'Goose Ready' : 'Ready')}
          </span>
        </div>
        <div className="flex items-center gap-4">
           <div className="hidden md:flex gap-1 items-center">
             {['⌃', '⌥', '⌘'].map((key, i) => (
               <div key={i} className="w-6 h-6 flex items-center justify-center rounded bg-secondary text-xs text-secondary-foreground border border-border/50">
                 {key}
               </div>
             ))}
             <div className="px-2 h-6 flex items-center justify-center rounded bg-secondary text-[10px] text-secondary-foreground border border-border/50">
               Space
             </div>
           </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
              "flex flex-col max-w-[85%]",
              msg.type === 'user' ? "ml-auto items-end" : "mr-auto items-start"
            )}
          >
            {/* Main message bubble */}
            <div className={cn(
              "p-4 rounded-2xl shadow-sm text-sm leading-relaxed select-text whitespace-pre-wrap",
              msg.type === 'user'
                ? "bg-[#272343] text-white rounded-tr-sm"
                : "bg-secondary/80 backdrop-blur-md text-foreground border border-border/50 rounded-tl-sm"
            )}>
              {msg.text}
            </div>

            {/* Memory cards - using expandable component */}
            {msg.memories && msg.memories.length > 0 && (
              <div className="mt-3 space-y-3 w-full">
                {msg.memories.map((memory, idx) => (
                  <MemoryCard key={idx} memory={memory} index={idx} />
                ))}
              </div>
            )}

            {/* Source tags */}
            {msg.sources && msg.sources.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {msg.sources.map(s => (
                  <div key={s} className="text-[10px] px-2 py-1 rounded-md bg-background/50 border border-border/30 text-muted-foreground flex items-center gap-1 truncate max-w-[150px]">
                    <Paperclip className="w-3 h-3 flex-shrink-0" />
                    <span className="truncate">{s}</span>
                  </div>
                ))}
              </div>
            )}

            <span className="text-[10px] text-muted-foreground mt-1 opacity-50">
              {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : ''}
            </span>
          </motion.div>
        ))}
        {(status === 'Searching' || status === 'Processing') && (
           <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mr-auto">
             <div className="bg-secondary/50 p-4 rounded-2xl rounded-tl-sm flex gap-1">
               <div className="w-2 h-2 bg-neon-blue rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
               <div className="w-2 h-2 bg-neon-blue rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
               <div className="w-2 h-2 bg-neon-blue rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
             </div>
           </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-border/40 backdrop-blur-md bg-background/30">
        <div className="relative flex items-center">
          <button className="absolute left-3 text-muted-foreground hover:text-neon-blue transition-colors">
            <Plus className="w-5 h-5" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask your second brain..."
            className="w-full bg-secondary/50 border border-border/50 rounded-xl py-3.5 pl-12 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-neon-blue/30 focus:border-neon-blue/50 transition-all shadow-inner"
          />
          <button
            onClick={handleSend}
            className="absolute right-2 p-1.5 bg-foreground text-background rounded-lg hover:scale-105 active:scale-95 transition-all"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <div className="text-center mt-2">
            <span className="text-[10px] text-muted-foreground/60">y=c is offline and private</span>
        </div>
      </div>
    </div>
  );
};

// 7. Settings View
const SettingsView = ({ darkMode, setDarkMode }: SettingsViewProps) => {
  const [purging, setPurging] = useState(false);
  const [purged, setPurged] = useState(false);

  const handlePurge = async () => {
    if (!confirm('Are you sure? This will permanently delete all memories.')) return;
    setPurging(true);
    try {
      await api.purgeMemories();
      setPurged(true);
      setTimeout(() => setPurged(false), 3000);
    } catch (err) {
      console.error('Purge failed:', err);
    } finally {
      setPurging(false);
    }
  };

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4">
      <h2 className="font-orbitron text-2xl font-bold mb-6">System Configuration</h2>

      <div className="space-y-4">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Appearance</h3>
        <div className="grid grid-cols-2 gap-4">
          <button
            onClick={() => setDarkMode(false)}
            className={cn("p-4 rounded-xl border-2 transition-all flex flex-col items-center gap-2", !darkMode ? "border-neon-blue bg-neon-blue/5" : "border-border hover:border-border/80")}
          >
            <div className="w-full h-20 bg-[#f0f0f0] rounded-lg shadow-sm mb-2" />
            <span className="text-sm font-medium">Light</span>
          </button>
          <button
            onClick={() => setDarkMode(true)}
            className={cn("p-4 rounded-xl border-2 transition-all flex flex-col items-center gap-2", darkMode ? "border-neon-blue bg-neon-blue/5" : "border-border hover:border-border/80")}
          >
            <div className="w-full h-20 bg-[#1e1c36] rounded-lg shadow-inner mb-2" />
            <span className="text-sm font-medium">Dark (Default)</span>
          </button>
        </div>
      </div>

      <div className="space-y-4 pt-8 border-t border-border/40">
        <h3 className="text-sm font-medium text-red-500 uppercase tracking-wider flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Danger Zone
        </h3>
        <div className="p-4 border border-red-500/20 bg-red-500/5 rounded-xl flex items-center justify-between">
          <div>
            <div className="font-medium text-sm">Purge Memory Index</div>
            <div className="text-xs text-muted-foreground">This action cannot be undone.</div>
          </div>
          <button
            onClick={handlePurge}
            disabled={purging}
            className="px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 text-xs font-medium rounded-lg border border-red-500/20 transition-colors disabled:opacity-50"
          >
            {purging ? <Loader2 className="w-3 h-3 animate-spin inline" /> : purged ? <><Check className="w-3 h-3 inline" /> Purged</> : 'Clear All'}
          </button>
        </div>
      </div>
    </div>
  );
};

// 8. Sources View
const SourcesView = () => {
  const [stats, setStats] = useState<{ total_chunks: number; by_type: Record<string, number>; source_count: number } | null>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await api.getStats();
        if (response.status === 'ok') {
          setStats(response.stats);
        }
      } catch (err) {
        console.error('Failed to fetch stats:', err);
      }
    };
    fetchStats();
  }, []);

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4">
      <h2 className="font-orbitron text-2xl font-bold mb-6">Indexed Sources</h2>

      {stats ? (
        <div className="space-y-6">
          {/* Overview Stats */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-secondary/30 rounded-xl p-4 border border-border/30">
              <div className="text-3xl font-orbitron font-bold text-neon-blue">
                {stats.total_chunks.toLocaleString()}
              </div>
              <div className="text-sm text-muted-foreground">Total Memory Chunks</div>
            </div>
            <div className="bg-secondary/30 rounded-xl p-4 border border-border/30">
              <div className="text-3xl font-orbitron font-bold text-neon-purple">
                {stats.source_count || Object.keys(stats.by_type).length}
              </div>
              <div className="text-sm text-muted-foreground">Unique Sources</div>
            </div>
          </div>

          {/* By Source Type */}
          <div className="bg-secondary/20 rounded-xl p-4 border border-border/30">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">By Source Type</h3>
            {Object.keys(stats.by_type).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(stats.by_type).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-secondary/50">
                        {type === 'claude' && <ClaudeIcon className="w-5 h-5 text-neon-purple" />}
                        {type === 'chatgpt' && <ChatGPTIcon className="w-5 h-5 text-neon-green" />}
                        {type === 'mac_notes' && <AppleNotesIcon className="w-5 h-5 text-neon-blue" />}
                        {!['claude', 'chatgpt', 'mac_notes'].includes(type) && <Layers className="w-5 h-5" />}
                      </div>
                      <span className="text-sm font-medium capitalize">{type.replace('_', ' ')}</span>
                    </div>
                    <span className="text-sm text-muted-foreground font-mono">{count} chunks</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-4">
                No sources indexed yet. Use "Ingest More" to add data.
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-40">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  );
};

// 9. Main App Controller
const INITIAL_MESSAGE: Message = {
  id: 1,
  type: 'bot',
  text: "Welcome to your second brain. Ask me anything from your past conversations and notes.\n\nTry something like:\n\n• \"What was I thinking about [topic]?\"\n• \"How did my ideas evolve on [project]?\"\n• \"Remind me about [concept]\"",
  timestamp: new Date()
};

// Generate unique ID for chat sessions
const generateId = () => `chat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

// Get title from first user message or use default
const getTitleFromMessages = (messages: Message[]): string => {
  const firstUserMessage = messages.find(m => m.type === 'user');
  if (firstUserMessage) {
    const title = firstUserMessage.text.slice(0, 40);
    return title.length < firstUserMessage.text.length ? `${title}...` : title;
  }
  return 'New Chat';
};

// Local storage keys
const STORAGE_VERSION = '2';
const STORAGE_KEYS = {
  VERSION: 'yc_storage_version',
  SESSIONS: 'yc_chat_sessions',
  ACTIVE_CHAT: 'yc_active_chat',
  ONBOARDED: 'yc_onboarded'
};

// Clear stale localStorage on version change
if (localStorage.getItem(STORAGE_KEYS.VERSION) !== STORAGE_VERSION) {
  localStorage.removeItem(STORAGE_KEYS.SESSIONS);
  localStorage.removeItem(STORAGE_KEYS.ACTIVE_CHAT);
  localStorage.removeItem(STORAGE_KEYS.ONBOARDED);
  localStorage.setItem(STORAGE_KEYS.VERSION, STORAGE_VERSION);
}

function App() {
  const [hasOnboarded, setHasOnboarded] = useState(() => {
    return localStorage.getItem(STORAGE_KEYS.ONBOARDED) === 'true';
  });
  const [isIngesting, setIsIngesting] = useState(false);
  const [filesToIngest, setFilesToIngest] = useState<UploadedFile[]>([]);
  const [activeView, setActiveView] = useState('chat');
  const [darkMode, setDarkMode] = useState(false);

  // Chat sessions management
  const [chatSessions, setChatSessions] = useState<ChatSession[]>(() => {
    const saved = localStorage.getItem(STORAGE_KEYS.SESSIONS);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return parsed.map((s: ChatSession) => ({
          ...s,
          createdAt: new Date(s.createdAt),
          updatedAt: new Date(s.updatedAt)
        }));
      } catch {
        return [];
      }
    }
    return [];
  });

  const [activeChatId, setActiveChatId] = useState<string | null>(() => {
    return localStorage.getItem(STORAGE_KEYS.ACTIVE_CHAT);
  });

  // Get current chat messages
  const currentChat = chatSessions.find(s => s.id === activeChatId);
  const chatMessages = currentChat?.messages || [INITIAL_MESSAGE];

  // Save sessions to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.SESSIONS, JSON.stringify(chatSessions));
  }, [chatSessions]);

  // Save active chat ID
  useEffect(() => {
    if (activeChatId) {
      localStorage.setItem(STORAGE_KEYS.ACTIVE_CHAT, activeChatId);
    }
  }, [activeChatId]);

  // Save onboarded status
  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.ONBOARDED, String(hasOnboarded));
  }, [hasOnboarded]);

  // Create new chat session
  const createNewChat = useCallback(() => {
    const newSession: ChatSession = {
      id: generateId(),
      title: 'New Chat',
      messages: [INITIAL_MESSAGE],
      createdAt: new Date(),
      updatedAt: new Date()
    };
    setChatSessions(prev => [newSession, ...prev]);
    setActiveChatId(newSession.id);
    setActiveView('chat');
  }, []);

  // Select a chat session
  const selectChat = useCallback((id: string) => {
    setActiveChatId(id);
    setActiveView('chat');
  }, []);

  // Delete a chat session
  const deleteChat = useCallback((id: string) => {
    setChatSessions(prev => prev.filter(s => s.id !== id));
    if (activeChatId === id) {
      const remaining = chatSessions.filter(s => s.id !== id);
      setActiveChatId(remaining.length > 0 ? remaining[0].id : null);
    }
  }, [activeChatId, chatSessions]);

  // Update messages for current chat
  const setChatMessages = useCallback((updater: Message[] | ((prev: Message[]) => Message[])) => {
    setChatSessions(prev => {
      // If no active chat, create one
      if (!activeChatId) {
        const newId = generateId();
        const newMessages = typeof updater === 'function' ? updater([INITIAL_MESSAGE]) : updater;
        const newSession: ChatSession = {
          id: newId,
          title: getTitleFromMessages(newMessages),
          messages: newMessages,
          createdAt: new Date(),
          updatedAt: new Date()
        };
        setActiveChatId(newId);
        return [newSession, ...prev];
      }

      return prev.map(session => {
        if (session.id === activeChatId) {
          const newMessages = typeof updater === 'function' ? updater(session.messages) : updater;
          return {
            ...session,
            messages: newMessages,
            title: getTitleFromMessages(newMessages),
            updatedAt: new Date()
          };
        }
        return session;
      });
    });
  }, [activeChatId]);

  // Auto-create first chat if none exists and user is onboarded
  useEffect(() => {
    if (hasOnboarded && chatSessions.length === 0) {
      createNewChat();
    }
  }, [hasOnboarded, chatSessions.length, createNewChat]);

  const startIngestion = (files: UploadedFile[]) => {
    setFilesToIngest(files);
    setIsIngesting(true);
  };

  const finishIngestion = () => {
    setIsIngesting(false);
    setHasOnboarded(true);
    setActiveView('chat');
    // Create first chat after onboarding
    if (chatSessions.length === 0) {
      createNewChat();
    }
  };

  // Handle "Ingest More" navigation
  const handleViewChange = (view: string) => {
    if (view === 'ingest') {
      setHasOnboarded(false);
      setActiveView('chat');
    } else {
      setActiveView(view);
    }
  };

  return (
    <WindowFrame darkMode={darkMode}>
      {!hasOnboarded && !isIngesting ? (
        <OnboardingView onStartIngestion={startIngestion} />
      ) : isIngesting ? (
        <IngestionView files={filesToIngest} onFinished={finishIngestion} />
      ) : (
        <>
          <Sidebar
            activeView={activeView}
            setActiveView={handleViewChange}
            chatSessions={chatSessions}
            activeChatId={activeChatId}
            onSelectChat={selectChat}
            onNewChat={createNewChat}
            onDeleteChat={deleteChat}
          />
          <main className="flex-1 bg-background/40 backdrop-blur-md relative">
             <AnimatePresence mode="wait">
               {activeView === 'chat' && (
                 <motion.div key="chat" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="h-full">
                    <ChatView messages={chatMessages} setMessages={setChatMessages} />
                 </motion.div>
               )}
               {activeView === 'settings' && (
                 <motion.div key="settings" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="h-full">
                    <SettingsView darkMode={darkMode} setDarkMode={setDarkMode} />
                 </motion.div>
               )}
               {activeView === 'files' && (
                 <motion.div key="files" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="h-full overflow-auto">
                    <SourcesView />
                 </motion.div>
               )}
             </AnimatePresence>
          </main>
        </>
      )}
    </WindowFrame>
  );
}

export default App;
