import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, Send, CheckCircle, Loader, AlertCircle, ThumbsUp, TrendingUp, HelpCircle } from 'lucide-react';
import api from '../api';

export default function Interview() {
  const [questions, setQuestions] = useState([]);
  const [targetRole, setTargetRole] = useState('');
  const [currentQIndex, setCurrentQIndex] = useState(0);
  const [userAnswer, setUserAnswer] = useState('');
  const [evaluation, setEvaluation] = useState(null);
  
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    restoreSession();
  }, []);

  const restoreSession = async () => {
    try {
      const { data } = await api.get('/interview/session');
      if (data && data.questions && data.questions.length > 0) {
        setQuestions(data.questions);
        setTargetRole(data.target_role || 'Software Engineer');
        
        // Restore progress index based on evaluated scores
        const evaluatedCount = (data.scores || []).length;
        if (evaluatedCount < data.questions.length) {
          setCurrentQIndex(evaluatedCount);
        } else {
          setCurrentQIndex(data.questions.length);
        }
      }
    } catch (err) {
      console.error("No active session to restore.");
    }
  };

  const generateQuestions = async () => {
    setLoadingQuestions(true);
    setError('');
    setQuestions([]);
    setEvaluation(null);
    setCurrentQIndex(0);
    setUserAnswer('');
    
    try {
      const { data } = await api.get('/interview/generate');
      setQuestions(data.questions);
      setTargetRole(data.target_role);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate questions.');
    } finally {
      setLoadingQuestions(false);
    }
  };

  const submitAnswer = async () => {
    if (!userAnswer.trim()) return;
    setEvaluating(true);
    setError('');
    
    try {
      const { data } = await api.post('/interview/evaluate', {
        question: questions[currentQIndex],
        answer: userAnswer,
        target_role: targetRole,
        question_index: currentQIndex,
      });
      setEvaluation(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to evaluate answer.');
    } finally {
      setEvaluating(false);
    }
  };

  const nextQuestion = () => {
    setUserAnswer('');
    setEvaluation(null);
    setCurrentQIndex(prev => prev + 1);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-4xl mx-auto space-y-6">
      
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex flex-col md:flex-row justify-between items-center gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <MessageSquare className="text-brand-500" /> AI Mock Interview (8 Questions: 5 Tech + 3 HR)
          </h2>
          <p className="text-sm text-gray-500">Personalized interview session based on your VTU skill gaps, weak points, and resume projects.</p>
        </div>
        <button onClick={generateQuestions} disabled={loadingQuestions} className="btn-modern min-w-[160px] flex justify-center items-center gap-2">
          {loadingQuestions ? <Loader className="animate-spin" size={20} /> : 'Start New Session'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl flex items-center gap-2 border border-red-100">
          <AlertCircle size={20} /> {error}
        </div>
      )}

      {questions.length > 0 && currentQIndex < questions.length && (
        <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm space-y-6">
          <div className="flex items-center justify-between border-b border-gray-100 pb-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-brand-600 uppercase tracking-wider">
                Question {currentQIndex + 1} of {questions.length}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-gray-100 text-gray-600">
                {currentQIndex < 5 ? 'Technical' : 'HR / Behavioral'}
              </span>
            </div>
            <span className="text-sm text-gray-400 font-medium">Role: {targetRole}</span>
          </div>
          
          <h3 className="text-xl font-medium text-gray-900 leading-snug">{questions[currentQIndex]}</h3>

          {!evaluation ? (
            <div className="space-y-4">
              <textarea
                className="input-modern min-h-[150px] resize-none"
                placeholder="Type your structured answer here..."
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                disabled={evaluating}
              />
              <button 
                onClick={submitAnswer} 
                disabled={evaluating || !userAnswer.trim()} 
                className="btn-modern w-full flex justify-center items-center gap-2"
              >
                {evaluating ? <Loader className="animate-spin" size={20} /> : <><Send size={18} /> Submit Answer</>}
              </button>
            </div>
          ) : (
            <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="space-y-5 bg-gray-50/90 p-6 rounded-xl border border-gray-200">
              <div className="flex items-center justify-between border-b border-gray-200/60 pb-3">
                <h4 className="font-bold text-gray-900 flex items-center gap-2">
                  <CheckCircle className="text-green-500" /> Answer Evaluation
                </h4>
                <div className={`px-4 py-1.5 rounded-full font-bold text-sm ${evaluation.score_out_of_10 >= 7 ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}`}>
                  Score: {evaluation.score_out_of_10} / 10
                </div>
              </div>
              
              {evaluation.strengths && (
                <div className="bg-green-50/60 p-4 rounded-lg border border-green-100">
                  <p className="text-xs font-bold uppercase tracking-wider text-green-800 mb-1 flex items-center gap-1.5">
                    <ThumbsUp size={14} /> Strengths:
                  </p>
                  <p className="text-gray-700 text-sm">{evaluation.strengths}</p>
                </div>
              )}

              {evaluation.improvements && (
                <div className="bg-amber-50/60 p-4 rounded-lg border border-amber-100">
                  <p className="text-xs font-bold uppercase tracking-wider text-amber-800 mb-1 flex items-center gap-1.5">
                    <TrendingUp size={14} /> Areas for Improvement:
                  </p>
                  <p className="text-gray-700 text-sm">{evaluation.improvements}</p>
                </div>
              )}

              {evaluation.feedback && (
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-1">Feedback Summary:</p>
                  <p className="text-gray-700 text-sm leading-relaxed">{evaluation.feedback}</p>
                </div>
              )}

              {evaluation.ideal_answer && (
                <div className="bg-blue-50/50 p-4 rounded-lg border border-blue-100">
                  <p className="text-xs font-bold uppercase tracking-wider text-blue-800 mb-1 flex items-center gap-1.5">
                    <HelpCircle size={14} /> Ideal Answer Hint:
                  </p>
                  <p className="text-gray-700 text-sm leading-relaxed">{evaluation.ideal_answer}</p>
                </div>
              )}

              <button onClick={nextQuestion} className="btn-modern w-full mt-4">
                {currentQIndex === questions.length - 1 ? 'Finish Interview' : 'Next Question'}
              </button>
            </motion.div>
          )}
        </div>
      )}

      {questions.length > 0 && currentQIndex === questions.length && (
        <div className="text-center py-16 bg-white rounded-2xl border border-gray-100 shadow-sm space-y-4">
          <CheckCircle className="mx-auto text-green-500" size={56} />
          <h3 className="text-2xl font-bold text-gray-900">Interview Session Complete!</h3>
          <p className="text-gray-500 max-w-md mx-auto text-sm">
            You've completed all 8 questions. Your answers and evaluation feedback are saved in your session.
          </p>
          <button onClick={generateQuestions} className="btn-modern mt-4">Start New Session</button>
        </div>
      )}
    </motion.div>
  );
}