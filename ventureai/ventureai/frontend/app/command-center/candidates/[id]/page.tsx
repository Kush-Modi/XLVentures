"use client";

import { use, useState } from "react";
import { motion } from "framer-motion";
import useSWR from "swr";
import { notFound } from "next/navigation";
import api from "@/lib/api";
import { cn, getInitials } from "@/lib/utils";
import { MapPin, Briefcase } from "lucide-react";

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton bg-[#4E5D5A]/10 animate-pulse", className)} />;
}

const TABS = ["Overview", "Skills", "Timeline", "Memory", "Recommendations"] as const;
type Tab = typeof TABS[number];

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function CandidateDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [activeTab, setActiveTab] = useState<Tab>("Overview");

  const { data: candidates, isLoading } = useSWR("candidates", api.getCandidates);
  const candidate = candidates?.find((c) => c.id === id);

  if (!isLoading && candidates && !candidate) notFound();
  if (isLoading) {
    return (
      <div className="p-6 space-y-4 text-[#4E5D5A]">
        <div className="flex items-center gap-4">
          <Skeleton className="w-16 h-16 rounded-2xl" />
          <div className="space-y-2"><Skeleton className="h-5 w-40 rounded" /><Skeleton className="h-4 w-32 rounded" /></div>
        </div>
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
      </div>
    );
  }
  if (!candidate) return null;

  return (
    <div className="p-6 text-[#4E5D5A] bg-[#F7F5EF] min-h-full">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-5 mb-6">
        <div className="w-16 h-16 rounded-2xl bg-[#4A6163] flex items-center justify-center text-[#F7F5EF] font-bold text-xl flex-shrink-0">
          {getInitials(candidate.name)}
        </div>
        <div>
          <h1 className="text-[#4E5D5A] font-bold text-xl">{candidate.name}</h1>
          <p className="text-[#6A756F]">{candidate.current_position}</p>
          <div className="flex items-center gap-4 mt-2 text-xs text-[#6A756F]/80">
            <span className="flex items-center gap-1"><Briefcase className="w-3 h-3" />{candidate.experience_years} years</span>
            <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{candidate.location}</span>
          </div>
        </div>
      </motion.div>

      <div className="flex items-center gap-1 mb-6 border-b border-[#4E5D5A]/10">
        {TABS.map((tab) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={cn("px-4 py-2 text-sm font-medium transition-all border-b-2 -mb-px",
              activeTab === tab ? "border-[#1D8F88] text-[#1D8F88]" : "border-transparent text-[#6A756F] hover:text-[#4E5D5A]")}>
            {tab}
          </button>
        ))}
      </div>

      <motion.div key={activeTab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        {activeTab === "Overview" && (
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/10 p-5 rounded-xl max-w-2xl shadow-sm">
            <h2 className="text-[#4E5D5A] font-medium text-sm mb-4">Resume Summary</h2>
            <p className="text-[#6A756F] text-sm leading-relaxed">{candidate.resume_text || "No resume summary available."}</p>
            <div className="mt-4 pt-4 border-t border-[#4E5D5A]/10 grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-[#6A756F]/70 text-xs">Experience</span><p className="text-[#4E5D5A] mt-0.5">{candidate.experience_years} years</p></div>
              <div><span className="text-[#6A756F]/70 text-xs">Location</span><p className="text-[#4E5D5A] mt-0.5">{candidate.location}</p></div>
              <div><span className="text-[#6A756F]/70 text-xs">Position</span><p className="text-[#4E5D5A] mt-0.5">{candidate.current_position}</p></div>
              <div><span className="text-[#6A756F]/70 text-xs">Status</span><p className="text-[#1D8F88] mt-0.5">Available</p></div>
            </div>
          </div>
        )}
        {activeTab === "Skills" && (
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/10 p-5 rounded-xl max-w-2xl shadow-sm">
            <h2 className="text-[#4E5D5A] font-medium text-sm mb-4">Skill Profile — {candidate.skills?.length} skills</h2>
            <div className="flex flex-wrap gap-2">
              {candidate.skills?.map((skill, i) => (
                <motion.span key={skill} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04 }}
                  className="px-3 py-1.5 rounded-lg text-sm border bg-[#EFE8DE] border-[#4E5D5A]/10 text-[#4E5D5A]">{skill}</motion.span>
              ))}
            </div>
          </div>
        )}
        {activeTab === "Timeline" && (
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/10 p-5 rounded-xl max-w-2xl shadow-sm">
            <h2 className="text-[#4E5D5A] font-medium text-sm mb-4">Knowledge Interactions</h2>
            <p className="text-[#6A756F] text-sm">Knowledge timeline is populated during agent analysis via Hybrid Retrieval.</p>
            <p className="text-[#6A756F]/70 text-xs mt-2 font-mono">Run Agent on this candidate to see interaction history.</p>
          </div>
        )}
        {activeTab === "Memory" && (
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/10 p-5 rounded-xl max-w-2xl shadow-sm">
            <h2 className="text-[#4E5D5A] font-medium text-sm mb-4">Planner Memory</h2>
            <p className="text-[#6A756F] text-sm">Memory context is loaded from Planner Memory during analysis.</p>
            <div className="mt-4 p-3 bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded-lg font-mono text-xs space-y-1">
              <p className="text-[#6A756F]">Candidate ID: {candidate.id}</p>
              <p className="text-[#6A756F]/70">Run analysis to compute memory score and feedback history.</p>
            </div>
          </div>
        )}
        {activeTab === "Recommendations" && (
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/10 p-5 rounded-xl max-w-2xl shadow-sm">
            <h2 className="text-[#4E5D5A] font-medium text-sm mb-4">AI Recommendations</h2>
            <p className="text-[#6A756F] text-sm">Go to Command Center → Select this candidate → Run Agent to generate recommendations.</p>
          </div>
        )}
      </motion.div>
    </div>
  );
}
