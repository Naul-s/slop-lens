"""Lexicons of language patterns that LLM-written copy over-produces (EN + KO).

Each entry is a regex fragment. These words are not wrong on their own; slop is
*density* — many of them stacked in short marketing copy with no specifics.
"""

CLICHE_EN = [
    r"elevat(e|es|ing)", r"seamless(ly)?", r"unleash\w*", r"unlock(s|ing)? (the|your)( full)? (power|potential)",
    r"empower(s|ing|ment)?", r"revolutioni[sz]\w*", r"cutting[- ]edge", r"next[- ]gen(eration)?",
    r"game[- ]chang\w+", r"supercharg\w+", r"effortless(ly)?", r"harness(ing)? the power",
    r"in today'?s (fast[- ]paced|digital|ever[- ]changing|modern)", r"transform(s|ing)? (the way|your)",
    r"to the next level", r"delv(e|es|ing)", r"\brobust\b", r"leverag(e|es|ing)", r"streamlin\w+",
    r"world[- ]class", r"state[- ]of[- ]the[- ]art", r"innovative", r"\bjourney\b", r"embark\w*",
    r"tapestry", r"\bbeacon\b", r"\brealm\b", r"ever[- ]evolving", r"unparalleled", r"unprecedented",
    r"all[- ]in[- ]one", r"one[- ]stop", r"look no further", r"whether you'?re an? [\w\s,]{1,40} or an?",
    r"at the (heart|forefront) of", r"take control of", r"\bstunning\b", r"crafted (with|for)",
    r"built for the (future|modern)", r"blazing(ly)?[- ]fast", r"lightning[- ]fast", r"peace of mind",
    r"made (simple|easy)", r"reimagin\w+", r"the future of", r"\bultimate\b", r"dive (in|into|deep)",
    r"skyrocket\w*", r"mission[- ]critical", r"synerg\w+", r"holistic", r"paradigm", r"\bpivotal\b",
    r"meticulous(ly)?", r"\bfoster(s|ing)?\b", r"navigat(e|ing) the", r"testament to", r"\bvibrant\b",
    r"\bcaptivating\b", r"\bimmersive\b", r"like never before", r"redefin\w+", r"boost your",
    r"\bscalable\b", r"\bintuitive\b", r"\bunlock\b", r"\bplethora\b", r"\bmyriad\b",
]

CLICHE_KO = [
    r"혁신적", r"차세대", r"원활한", r"손쉽게", r"간편하게", r"한 단계 (더 )?(높은|업그레이드|나아간)",
    r"새로운 차원", r"극대화", r"최적화된", r"완벽한 (솔루션|경험|선택)", r"지금 (바로 )?시작하세요",
    r"여정", r"경험을 선사", r"놀라운 (경험|성능|결과)", r"강력한 (기능|성능|도구)", r"스마트한",
    r"올인원", r"무한한 가능성", r"미래를 (열|만들|선도|여는)", r"압도적", r"획기적",
    r"선도하는", r"차별화된", r"원스톱", r"맞춤형 솔루션", r"새로운 기준", r"게임 체인저",
    r"비교할 수 없는", r"몰입감 넘치는", r"당신만을 위한", r"상상 그 이상", r"한계를 (넘|뛰어넘)",
    r"잠재력을 (깨우|발휘|끌어|극대화)", r"놓치지 마세요", r"경험해 ?보세요", r"만나보세요",
    r"모든 것을 한 ?곳에서?", r"쉽고 빠르게", r"더 스마트하게", r"새로운 시대", r"혁신을 (경험|만나)",
    r"효율성을 (높|극대화)", r"생산성을 (높|극대화|향상)",
]

STOCK_NAMES = [
    "Sarah Johnson", "Sarah Chen", "Sarah Mitchell", "Sarah Williams", "Michael Chen", "Michael Brown",
    "Emily Rodriguez", "Emily Chen", "Emily Davis", "David Kim", "David Park", "David Chen",
    "Alex Thompson", "Alex Rivera", "Alex Morgan", "Jessica Lee", "John Smith", "Jane Doe", "John Doe",
    "Jane Smith", "Emma Wilson", "James Wilson", "Lisa Wang", "Mark Davis", "Priya Patel", "Marcus Johnson",
    "Olivia Martinez", "Daniel Park", "Sophia Lee", "Chris Taylor", "Amanda Foster", "Ryan Mitchell",
    "Jennifer Lee", "Robert Chen", "Maria Garcia", "Lisa Chen", "Tom Anderson", "Rachel Kim",
    "김민수", "이지은", "박지훈", "홍길동", "김철수", "이영희", "김지현", "박서준", "이민호", "최지우",
]

STOCK_SECTIONS = {
    "hero": r"\bhero\b",
    "features": r"\bfeatures?\b|key features|why choose|주요 기능|핵심 기능|특징",
    "how_it_works": r"how it works|how does it work|\bsteps?\b.*(get started|simple)|이용 방법|사용 방법|어떻게 작동",
    "testimonials": r"testimonials?|what (our )?(customers|users|clients) (say|are saying)|loved by|reviews|고객 후기|사용자 후기|이용 후기|리뷰",
    "pricing": r"\bpricing\b|choose (your|a) plan|simple,? transparent pricing|\bplans\b|요금제|가격|플랜",
    "faq": r"\bfaq\b|frequently asked|자주 묻는 질문",
    "cta": r"\bcta\b|ready to (get started|transform|start|begin|join)|get started today|start your|지금 시작|시작해 ?보세요",
    "stats": r"\bstats?\b|by the numbers|숫자로 보는",
    "logos": r"trusted by|used by (teams|companies)|logo[s-]?(cloud|wall|grid)|함께하는 (기업|파트너)|신뢰하는",
    "newsletter": r"newsletter|stay (updated|in the loop)|subscribe|뉴스레터|구독",
    "team": r"meet (the|our) team|\bour team\b|팀 소개",
    "integrations": r"integrations?|connect with your favorite|연동",
}

CTA_GENERIC = (
    r"\b(get started( for free| now| today)?|learn more|start (your )?free trial|sign up( for)?( free)?|"
    r"try (it )?(for )?free|book a demo|request a demo|join (now|today|the waitlist)|explore (now|more)|"
    r"discover more|contact us)\b|시작하기|자세히 ?보기|무료로 시작|지금 시작|더 알아보기|문의하기|체험하기"
)

HEADLINE_FORMULAS = (
    r"reimagined|the future of|all[- ]in[- ]one|everything you need|made (simple|easy)|supercharge|"
    r"welcome to|unlock|elevate|transform your|build (better|faster)|at scale|for (the )?modern|"
    r"like never before|redefin|next[- ]level|the (smarter|better|easiest|fastest) way|your (ultimate|all)|"
    r"meets|powered by ai|ai-powered|미래|새로운 시대|한 곳에서|쉽고 빠르게|더 스마트하게|모든 것|"
    r"새로운 경험|혁신|차세대|완벽한"
)

GENERIC_TITLES = {
    "document", "react app", "vite + react", "vite + react + ts", "vite app", "vite + vue", "vite + svelte",
    "my website", "my app", "landing page", "untitled", "home", "index", "game", "my game", "new tab",
    "next.js app", "create next app", "app", "website", "page title", "title", "html5 game", "canvas game",
}
