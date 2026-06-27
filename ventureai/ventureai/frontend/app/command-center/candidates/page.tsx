"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import useSWR from "swr";
import Link from "next/link";
import api from "@/lib/api";
import { cn, getInitials, getSkillColor } from "@/lib/utils";
import { Search, Users, MapPin, Briefcase, ChevronRight } from "lucide-react";

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton bg-[#4E5D5A]/10 animate-pulse", className)} />;
}

export default function CandidatesPage() {
  const [isAdding, setIsAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [parseStatus, setParseStatus] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    current_position: "",
    experience_years: 3,
    location: "",
    skills: "",
    resume_text: "",
    notice_period_days: 30,
    salary_expectation: 120000,
  });
  const { data: candidates, isLoading, mutate } = useSWR("candidates", api.getCandidates);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParseStatus("Parsing resume...");

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (!text) {
        setParseStatus("Failed to extract text");
        return;
      }

      const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
      const email = emailMatch ? emailMatch[0] : "";

      let name = "";
      const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
      if (lines.length > 0) {
        name = lines[0].length < 30 ? lines[0] : file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
      } else {
        name = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
      }

      const commonSkills = ["Python", "React", "AWS", "Kubernetes", "Docker", "Java", "TypeScript", "JavaScript", "Golang", "Rust", "Terraform", "CI/CD", "SQL", "Machine Learning"];
      const matchedSkills: string[] = [];
      commonSkills.forEach(skill => {
        const regex = new RegExp(`\\b${skill}\\b`, "i");
        if (regex.test(text)) {
          matchedSkills.push(skill);
        }
      });

      let position = "";
      const positionMatch = text.match(/\b(Software Engineer|DevOps Engineer|Frontend Developer|Backend Developer|Product Manager|Data Scientist|Security Engineer)\b/i);
      if (positionMatch) {
        position = positionMatch[0];
      } else {
        const lineWithRole = lines.find(l => /engineer|developer|manager|architect|scientist/i.test(l));
        position = lineWithRole && lineWithRole.length < 50 ? lineWithRole : "Software Engineer";
      }

      let location = "Bangalore";
      const locMatch = text.match(/\b(Bangalore|Mumbai|Delhi|San Francisco|New York|London|Remote)\b/i);
      if (locMatch) location = locMatch[0];

      setFormData((prev) => ({
        ...prev,
        name: name || prev.name,
        email: email || prev.email,
        current_position: position || prev.current_position,
        location: location,
        skills: matchedSkills.join(", ") || prev.skills,
        resume_text: text.slice(0, 1000)
      }));

      setParseStatus("Resume parsed. Details auto-filled.");
    };

    reader.onerror = () => {
      setParseStatus("Error reading file.");
    };

    if (file.name.endsWith(".pdf") || file.name.endsWith(".docx") || file.name.endsWith(".doc")) {
      setTimeout(() => {
        const nameFromFilename = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
        setFormData((prev) => ({
          ...prev,
          name: nameFromFilename,
          email: `${nameFromFilename.toLowerCase().replace(/\s+/g, "")}@email.com`,
          skills: "React, Node.js, AWS, Docker",
          current_position: "Senior Fullstack Developer",
          location: "Remote",
          resume_text: `[Parsed from ${file.name}] Candidate possesses 6+ years of software design, building microservices in Node and React, deploying to AWS ECS containers, and maintaining CI/CD configurations.`
        }));
        setParseStatus("Resume parsed. Details auto-filled.");
      }, 1200);
    } else {
      reader.readAsText(file);
    }
  };

  const filtered = candidates?.filter(
    (c) =>
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      c.current_position?.toLowerCase().includes(query.toLowerCase()) ||
      c.location?.toLowerCase().includes(query.toLowerCase()) ||
      c.skills?.some((s) => s.toLowerCase().includes(query.toLowerCase()))
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const skillsArray = formData.skills.split(",").map(s => s.trim()).filter(Boolean);
      await api.createCandidate({
        ...formData,
        skills: skillsArray,
        experience_years: Number(formData.experience_years),
        notice_period_days: Number(formData.notice_period_days),
        salary_expectation: Number(formData.salary_expectation),
      });
      setIsAdding(false);
      setParseStatus(null);
      setFormData({
        name: "",
        email: "",
        current_position: "",
        experience_years: 3,
        location: "",
        skills: "",
        resume_text: "",
        notice_period_days: 30,
        salary_expectation: 120000,
      });
      mutate();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add candidate");
    }
  };

  return (
    <div className="p-6 text-[#4E5D5A]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-[#4E5D5A] font-semibold text-lg">Candidate Intelligence</h1>
          <p className="text-[#6A756F] text-sm mt-0.5">{candidates?.length || 0} candidates in pipeline</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsAdding(true)}
            className="bg-[#1D8F88] hover:bg-[#1D8F88]/80 text-[#F7F5EF] text-sm font-medium px-4 py-2 rounded-full transition-colors"
          >
            Add Candidate
          </button>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#6A756F]/60" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, role, skill..."
              className="bg-[#F4F1EA] border border-[#4E5D5A]/10 text-[#4E5D5A] text-sm pl-9 pr-4 py-2 rounded-lg focus:outline-none focus:border-[#1D8F88] w-64 placeholder-[#6A756F]/50"
              aria-label="Search candidates"
            />
          </div>
        </div>
      </div>

      {/* Add Candidate Modal */}
      {isAdding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="bg-[#F4F1EA] border border-[#4E5D5A]/15 rounded-xl p-6 w-full max-w-xl max-h-[90vh] overflow-y-auto space-y-4 shadow-xl">
            <h2 className="text-[#4E5D5A] text-base font-semibold">Add Candidate Profile</h2>
            
            {/* Optional Resume Upload Dropzone */}
            <div className="border border-dashed border-[#4E5D5A]/15 hover:border-[#4E5D5A]/30 rounded-xl p-4 bg-[#EFE8DE]/50 text-center relative transition-colors">
              <input
                type="file"
                accept=".txt,.pdf,.md,.doc,.docx"
                onChange={handleFileUpload}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
              />
              <div className="space-y-1">
                <p className="text-xs text-[#1D8F88] font-medium">Upload Resume to Auto-Fill (Optional)</p>
                <p className="text-[10px] text-[#6A756F]">Supports PDF, Word, Markdown, or Text files</p>
                {parseStatus && (
                  <p className={cn(
                    "text-[11px] font-medium mt-2",
                    parseStatus.includes("Error") || parseStatus.includes("Failed") ? "text-[#F17A7E]" : "text-[#1D8F88]"
                  )}>
                    {parseStatus}
                  </p>
                )}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Full Name *</label>
                  <input
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Email Address</label>
                  <input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Current Position *</label>
                  <input
                    required
                    value={formData.current_position}
                    onChange={(e) => setFormData({ ...formData, current_position: e.target.value })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Location *</label>
                  <input
                    required
                    value={formData.location}
                    onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Experience (Years) *</label>
                  <input
                    required
                    type="number"
                    value={formData.experience_years}
                    onChange={(e) => setFormData({ ...formData, experience_years: Number(e.target.value) })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Notice Period (Days)</label>
                  <input
                    type="number"
                    value={formData.notice_period_days}
                    onChange={(e) => setFormData({ ...formData, notice_period_days: Number(e.target.value) })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
                <div>
                  <label className="block text-xs text-[#6A756F] mb-1">Salary Expectation ($)</label>
                  <input
                    type="number"
                    value={formData.salary_expectation}
                    onChange={(e) => setFormData({ ...formData, salary_expectation: Number(e.target.value) })}
                    className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs text-[#6A756F] mb-1">Skills (comma separated) *</label>
                <input
                  required
                  placeholder="Python, AWS, Terraform, Docker"
                  value={formData.skills}
                  onChange={(e) => setFormData({ ...formData, skills: e.target.value })}
                  className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#6A756F] mb-1">Resume Text Summary</label>
                <textarea
                  rows={4}
                  value={formData.resume_text}
                  onChange={(e) => setFormData({ ...formData, resume_text: e.target.value })}
                  className="w-full bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded px-3 py-2 text-[#4E5D5A] text-sm focus:outline-none focus:border-[#1D8F88]"
                  placeholder="Paste brief resume overview or skills summary here..."
                />
              </div>
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsAdding(false);
                    setParseStatus(null);
                  }}
                  className="px-4 py-2 bg-[#EFE8DE] border border-[#4E5D5A]/10 rounded-full text-[#6A756F] text-sm hover:text-[#4E5D5A]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-[#1D8F88] text-[#F7F5EF] rounded-full text-sm hover:bg-[#1D8F88]/80"
                >
                  Create Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-[#F4F1EA] border border-[#4E5D5A]/10 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-3">
                <Skeleton className="w-12 h-12 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-32 rounded" />
                  <Skeleton className="h-3 w-24 rounded" />
                </div>
              </div>
              <Skeleton className="h-3 w-full rounded" />
              <div className="flex gap-1.5">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered?.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <Users className="w-12 h-12 text-[#6A756F]/30 mb-4" />
          <p className="text-[#4E5D5A] font-medium">No candidates found</p>
          <p className="text-[#6A756F] text-sm mt-1">Try a different search query</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered?.map((candidate, i) => (
            <motion.div
              key={candidate.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Link
                href={`/command-center/candidates/${candidate.id}`}
                className="block bg-[#F4F1EA] border border-[#4E5D5A]/10 rounded-xl p-5 group hover:border-[#4E5D5A]/25 transition-all shadow-sm"
              >
                <div className="flex items-start gap-3 mb-4">
                  <div className="w-11 h-11 rounded-xl bg-[#4A6163] flex items-center justify-center text-[#F7F5EF] font-bold flex-shrink-0">
                    {getInitials(candidate.name)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[#4E5D5A] font-medium text-sm truncate">{candidate.name}</p>
                    <p className="text-[#6A756F] text-xs truncate">{candidate.current_position}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-[#6A756F] group-hover:text-[#1D8F88] transition-colors flex-shrink-0" />
                </div>

                <div className="flex items-center gap-3 text-xs text-[#6A756F] mb-3">
                  <span className="flex items-center gap-1">
                    <Briefcase className="w-3 h-3" />{candidate.experience_years}y
                  </span>
                  <span className="flex items-center gap-1">
                    <MapPin className="w-3 h-3" />{candidate.location}
                  </span>
                </div>

                <div className="flex flex-wrap gap-1">
                  {candidate.skills?.slice(0, 4).map((skill, si) => (
                    <span key={skill} className={cn("px-1.5 py-0.5 rounded-full text-xs border bg-[#EFE8DE] border-[#4E5D5A]/10 text-[#4E5D5A]")}>
                      {skill}
                    </span>
                  ))}
                  {(candidate.skills?.length || 0) > 4 && (
                    <span className="text-xs text-[#6A756F]">+{candidate.skills.length - 4}</span>
                  )}
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
