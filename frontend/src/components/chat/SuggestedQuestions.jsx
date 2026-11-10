import { ArrowUpRight } from 'lucide-react'
import { suggestedQuestions } from '../../data/suggestedQuestions'
export default function SuggestedQuestions({ onSelect }) { return <div className="suggestions">{suggestedQuestions.map((question) => <button key={question} onClick={() => onSelect(question)}><span>{question}</span><ArrowUpRight size={17} /></button>)}</div> }
