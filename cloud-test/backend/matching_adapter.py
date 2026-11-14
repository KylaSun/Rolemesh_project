"""Opt-in FastAPI router for Qi's authenticated repository integration.

The existing main.app and /demo/* are unchanged. There are deliberately no
default identity, permission policy, candidate query or database credentials.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from rolemesh_matching.integration import ContractError
from rolemesh_matching.service import run_matching_service

logger = logging.getLogger(__name__)


class ProfileQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_id: str = Field(strict=True, min_length=1, max_length=128, pattern=r'\S')


class RoleQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role_id: str = Field(strict=True, min_length=1, max_length=128, pattern=r'\S')


def create_matching_router(*, get_principal, authorize_profile, authorize_role,
                           load_profile, load_roles, load_role, load_profiles,
                           max_candidates=1000):
    """Callbacks receive (principal, resource_id), except load_roles(principal).

    Permission callbacks must explicitly return True. Loaders return trusted
    DTOs, with visibility/consent/project-lifecycle filters already applied.
    """
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError('max_candidates must be a positive integer')
    router = APIRouter(prefix='/matching', tags=['Matching integration adapter'])

    def execute(principal, query, direction):
        if principal is None:
            raise HTTPException(status_code=401, detail='Authentication required')
        try:
            if direction == 'projects':
                if authorize_profile(principal, query.profile_id) is not True:
                    raise HTTPException(status_code=403, detail='Profile access denied')
                profile = load_profile(principal, query.profile_id)
                if profile is None:
                    raise HTTPException(status_code=404, detail='Profile not found')
                if profile.get('profile_id') != query.profile_id:
                    raise ValueError('Repository profile identity mismatch')
                roles = load_roles(principal)
                if not isinstance(roles, list) or len(roles) > max_candidates:
                    raise ValueError('Repository candidate limit or type invalid')
                request = {'contract_version':'0.1.0','profile':profile,'roles':roles}
            else:
                if authorize_role(principal, query.role_id) is not True:
                    raise HTTPException(status_code=403, detail='Role access denied')
                role = load_role(principal, query.role_id)
                if role is None:
                    raise HTTPException(status_code=404, detail='Role not found')
                if role.get('role_id') != query.role_id:
                    raise ValueError('Repository role identity mismatch')
                profiles = load_profiles(principal, query.role_id)
                if not isinstance(profiles, list) or len(profiles) > max_candidates:
                    raise ValueError('Repository candidate limit or type invalid')
                request = {'contract_version':'0.1.0','role':role,'profiles':profiles}
            return {'data':run_matching_service(request,direction=direction)}
        except HTTPException:
            raise
        except ContractError as error:
            logger.error('Matching repository contract error: %s',error.code)
            raise HTTPException(status_code=500, detail='Stored matching data violates contract') from error
        except (ValueError, TypeError, KeyError) as error:
            logger.error('Matching repository error: %s',type(error).__name__)
            raise HTTPException(status_code=500, detail='Invalid matching repository data') from error
        except Exception as error:
            logger.error('Matching service unavailable: %s',type(error).__name__)
            raise HTTPException(status_code=503, detail='Matching service unavailable') from error

    @router.post('/projects')
    def matching_projects(body: ProfileQuery, response: Response, principal=Depends(get_principal)):
        response.headers['Cache-Control'] = 'no-store'
        return execute(principal,body,'projects')

    @router.post('/profiles')
    def matching_profiles(body: RoleQuery, response: Response, principal=Depends(get_principal)):
        response.headers['Cache-Control'] = 'no-store'
        return execute(principal,body,'profiles')

    return router
