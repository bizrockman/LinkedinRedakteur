"""OnboardingWizard — orchestriert die 5 Steps und persistiert das Resultat."""

from __future__ import annotations

import logging

from eve.core.entities import (
    AgentIdentity,
    ClientProfile,
)
from eve.core.ports import LLMProvider, PromptRepository
from eve.use_cases.onboarding.state import WizardState
from eve.use_cases.onboarding.steps.step_01_mode import ChooseModeStep
from eve.use_cases.onboarding.steps.step_02_basic_info import BasicInfoStep
from eve.use_cases.onboarding.steps.step_03_topics import TopicsStep
from eve.use_cases.onboarding.steps.step_04_audience import AudienceStep
from eve.use_cases.onboarding.steps.step_05_posts import TopPostsStep
from eve.use_cases.onboarding.steps.step_06_personas import PersonasStep
from eve.use_cases.onboarding.steps.step_07_telegram import TelegramMockStep
from eve.use_cases.onboarding.steps.step_08_linkedin import LinkedInMockStep
from eve.use_cases.onboarding.ui import WizardUI

log = logging.getLogger(__name__)

DEFAULT_NOGOS = [
    'Sag niemals "revolutionieren" oder "Stell dir vor"',
    "Nutze niemals Emojis",
    "Niemals Hashtags",
]


class OnboardingWizard:
    """Führt einen User durch das vollständige Onboarding und speichert
    am Ende das Profil + Posts-Sidecar."""

    def __init__(
        self,
        ui: WizardUI,
        llm: LLMProvider,
        prompts: PromptRepository,
        *,
        llm_model: str = "claude-opus-4-7",
    ) -> None:
        self.ui = ui
        self.llm = llm
        self.prompts = prompts
        self.llm_model = llm_model

    async def run(self, profile_id: str) -> ClientProfile:
        state = WizardState(
            profile_id=profile_id,
            profile=ClientProfile(
                profile_id=profile_id,
                agent=AgentIdentity(),  # Default-Eve-Identität
                nogos=DEFAULT_NOGOS[:],
            ),
        )

        await self.ui.info(f"Onboarding für Profil-ID: {profile_id}\n")

        state = await ChooseModeStep(self.ui).run(state)
        state = await BasicInfoStep(self.ui).run(state)
        state = await TopicsStep(self.ui, self.llm, self.prompts, model=self.llm_model).run(state)
        state = await AudienceStep(self.ui, self.llm, self.prompts, model=self.llm_model).run(state)
        state = await TopPostsStep(self.ui, self.prompts).run(state)
        state = await PersonasStep(self.ui, self.llm, self.prompts, model=self.llm_model).run(state)
        state = await TelegramMockStep(self.ui).run(state)
        state = await LinkedInMockStep(self.ui).run(state)

        saved = await self.prompts.save_profile(state.profile)
        await self.ui.info(
            f"\n✓ Profil gespeichert: prompts/profiles/{saved.profile_id}.yaml"
        )
        if state.stored_posts:
            await self.ui.info(
                f"✓ Posts gespeichert:  prompts/profiles/{saved.profile_id}.posts.json"
            )
        return saved
