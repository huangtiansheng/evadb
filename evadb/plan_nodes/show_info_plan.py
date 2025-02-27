# coding=utf-8
# Copyright 2018-2023 EvaDB
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Optional

from evadb.parser.types import ShowType
from evadb.plan_nodes.abstract_plan import AbstractPlan
from evadb.plan_nodes.types import PlanOprType


class ShowInfoPlan(AbstractPlan):
    def __init__(self, show_type: ShowType, show_val: Optional[str] = ""):
        self._show_type = show_type
        self._show_val = show_val
        super().__init__(PlanOprType.SHOW_INFO)

    @property
    def show_type(self):
        return self._show_type

    @property
    def show_val(self):
        return self._show_val

    def __str__(self):
        if self._show_type == ShowType.FUNCTIONS:
            return "ShowFunctionPlan"
        if self._show_type == ShowType.DATABASES:
            return "ShowDatabasePlan"
        elif self._show_type == ShowType.TABLES:
            return "ShowTablePlan"
        elif self._show_type == ShowType.CONFIGS:
            return "ShowConfigPlan"

    def __hash__(self) -> int:
        return hash((super().__hash__(), self.show_type, self.show_val))
